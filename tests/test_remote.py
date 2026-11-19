import json
import tempfile
import time
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
from starlette.testclient import TestClient

from consumer_cad_ai.remote import RemoteConfig, remote_settings
from consumer_cad_ai.server import create_server


class RemoteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.signer = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.cfg = RemoteConfig("https://cad.example/mcp", "https://id.example/realm",
                                "https://id.example/realm/keys", "cad-owner", "chat-client")
        settings = remote_settings(self.cfg)
        self.assertEqual(settings["host"], "127.0.0.1")
        keys = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.signer.public_key()))
        keys.update(kid="one", alg="RS256", use="sig")
        get_keys = patch.object(settings["token_verifier"].jwks, "get_signing_keys", return_value=[jwt.PyJWK(keys)])
        get_keys.start()
        self.addCleanup(get_keys.stop)
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.enterContext(patch.dict("os.environ", {"CAD_WORKSPACE": workspace.name}))
        server = create_server(**settings)
        self.server_name = server.name
        self.http = TestClient(server.streamable_http_app(), base_url="https://cad.example")
        self.http.__enter__()
        self.addCleanup(self.http.__exit__, None, None, None)

    def token(self, *, signer=None, typ="at+jwt", **overrides):
        claims = dict(iss=self.cfg.issuer, aud=self.cfg.resource, sub=self.cfg.subject,
                      client_id=self.cfg.client, exp=int(time.time()) + 3600, scope="cad:design")
        return jwt.encode(claims | overrides, signer or self.signer, algorithm="RS256",
                          headers={"kid": "one", "typ": typ})

    def post(self, token=None, **extra):
        headers = {"Accept": "application/json, text/event-stream"}
        if token:
            headers["Authorization"] = "Bearer " + token
        return self.http.post("/mcp", headers=headers | extra, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                       "clientInfo": {"name": "test", "version": "1"}},
        })

    def test_challenge_and_discovery(self):
        response = self.post()
        self.assertEqual(response.status_code, 401)
        path = "/.well-known/oauth-protected-resource/mcp"
        self.assertIn(path, response.headers["WWW-Authenticate"])
        metadata = self.http.get(path).json()
        self.assertEqual(metadata["resource"], self.cfg.resource)
        self.assertEqual(metadata["authorization_servers"], [self.cfg.issuer])
        self.assertIn("cad:design", metadata["scopes_supported"])

    def test_valid_access_token_and_transport(self):
        response = self.post(self.token())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["result"]["serverInfo"]["name"], self.server_name)
        discovery = self.http.post("/mcp", headers={
            "Accept": "application/json, text/event-stream", "Authorization": "Bearer " + self.token()
        }, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(discovery.status_code, 200)
        names = {tool["name"] for tool in discovery.json()["result"]["tools"]}
        self.assertIn("check_custom", names)
        checked = self.http.post("/mcp", headers={
            "Accept": "application/json, text/event-stream", "Authorization": "Bearer " + self.token()
        }, json={"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "check_custom", "arguments": {"spec": {"parts": [{
                "name": "plate", "material": "Aluminium",
                "features": [{"kind": "box", "size": [12, 8, 2]}],
            }]}}
        }})
        self.assertEqual(checked.status_code, 200)
        payload = checked.json()["result"]
        self.assertFalse(payload.get("isError"), payload)
        result = json.loads(payload["content"][0]["text"])
        self.assertTrue(result["passed"])
        self.assertEqual(result["dimensions_mm"]["assembly_xyz"], [12, 8, 2])
        self.assertEqual(self.post(self.token(), Origin="https://foreign.example").status_code, 403)

    def test_rejected_tokens(self):
        for changes in ({"iss": "https://wrong"}, {"aud": "other-api"}, {"sub": "another-user"},
                        {"client_id": "another-client"}, {"exp": 0}, {"signer": self.other_key},
                        {"typ": "JWT"}):
            with self.subTest(changed=tuple(changes)):
                self.assertEqual(self.post(self.token(**changes)).status_code, 401)
        self.assertEqual(self.post(self.token(scope="other")).status_code, 403)

    def test_configuration_fails_closed(self):
        with patch.dict("os.environ", {}, clear=True), self.assertRaisesRegex(ValueError, "Missing"):
            RemoteConfig.from_env()
        with self.assertRaises(ValueError):
            RemoteConfig("http://localhost/mcp", self.cfg.issuer, self.cfg.jwks, "owner", "client")
