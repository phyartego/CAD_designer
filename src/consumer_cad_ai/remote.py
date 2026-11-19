"""Single-operator, OAuth-protected HTTP transport for the CAD tools."""
from dataclasses import dataclass
import os
from urllib.parse import urlsplit

import anyio
import jwt
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings


SCOPE = "cad:design"


def _https_url(name, value):
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.fragment or parsed.query or "*" in value):
        raise ValueError(f"{name} must be an absolute HTTPS URL without credentials, wildcards, query or fragment")
    return parsed


@dataclass(frozen=True)
class RemoteConfig:
    resource: str
    issuer: str
    jwks: str
    subject: str
    client: str
    port: int = 8765

    def __post_init__(self):
        if _https_url("CAD_RESOURCE_URL", self.resource).path != "/mcp":
            raise ValueError("CAD_RESOURCE_URL must end in /mcp")
        _https_url("CAD_OAUTH_ISSUER", self.issuer)
        _https_url("CAD_OAUTH_JWKS_URL", self.jwks)
        if not self.subject.strip() or not self.client.strip():
            raise ValueError("Configure a single OAuth subject and client for this workspace")
        if not 0 < self.port <= 65535:
            raise ValueError("CAD_REMOTE_PORT must be between 1 and 65535")

    @classmethod
    def from_env(cls):
        names = ("CAD_RESOURCE_URL", "CAD_OAUTH_ISSUER", "CAD_OAUTH_JWKS_URL",
                 "CAD_OAUTH_SUBJECT", "CAD_OAUTH_CLIENT_ID")
        missing = [name for name in names if not os.environ.get(name)]
        if missing:
            raise ValueError("Missing remote configuration: " + ", ".join(missing))
        return cls(*(os.environ[name] for name in names), port=int(os.environ.get("CAD_REMOTE_PORT", 8765)))


class CadTokenVerifier:
    def __init__(self, config):
        self.config = config
        self.jwks = jwt.PyJWKClient(config.jwks, lifespan=300, timeout=5)
        self._lookup_lock = anyio.Lock()

    async def verify_token(self, token: str) -> AccessToken | None:
        if len(token) > 16384:
            return None
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if header.get("alg") != "RS256" or not isinstance(kid, str) or not kid:
                return None
            # Look only in the configured provider's cached keys. Arbitrary key
            # identifiers cannot force extra network refreshes of a valid cache.
            async with self._lookup_lock:
                keys = await anyio.to_thread.run_sync(self.jwks.get_signing_keys)
            key = next((k for k in keys if k.key_id == kid and k.algorithm_name == "RS256"), None)
            if key is None:
                return None
            claims = jwt.decode(token, key.key, algorithms=["RS256"], issuer=self.config.issuer,
                                audience=self.config.resource,
                                options={"require": ["exp", "iss", "aud", "sub"]})
            # Accept RFC 9068 ATs and Keycloak's signed access-token marker.
            access_type = header.get("typ") in ("at+jwt", "application/at+jwt") or claims.get("typ") == "Bearer"
            client = claims.get("client_id") or claims.get("azp")
            scopes = claims.get("scope", "")
            if (not access_type or claims["sub"] != self.config.subject or client != self.config.client
                    or not isinstance(scopes, str)):
                return None
            return AccessToken(token=token, client_id=client, scopes=scopes.split(),
                               expires_at=claims["exp"], subject=claims["sub"], resource=self.config.resource)
        except (jwt.PyJWTError, TypeError, ValueError, OverflowError):
            return None


def remote_settings(config):
    public = urlsplit(config.resource)
    return dict(
        host="127.0.0.1", port=config.port, stateless_http=True, json_response=True,
        token_verifier=CadTokenVerifier(config),
        auth=AuthSettings(issuer_url=config.issuer, resource_server_url=config.resource, required_scopes=[SCOPE]),
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True, allowed_hosts=[public.netloc],
            allowed_origins=[f"https://{public.netloc}", "https://chatgpt.com"],
        ),
    )


def serve_remote():
    from .server import create_server

    server = create_server(**remote_settings(RemoteConfig.from_env()))
    server.run(transport="streamable-http")
