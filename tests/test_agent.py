"""Drive the installed MCP protocol over a real stdio subprocess."""

import base64
from datetime import timedelta
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import ImageContent, TextContent


ROOT = Path(__file__).resolve().parents[1]


class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def json_tool(self, session, name, **arguments):
        result = await session.call_tool(name, arguments)
        self.assertFalse(result.isError, str(result.content)[:1200])
        if result.structuredContent is not None:
            return result.structuredContent
        block = next(item for item in result.content if isinstance(item, TextContent))
        return json.loads(block.text)

    async def test_agent_repairs_geometry_and_downloads_real_artifacts(self):
        with tempfile.TemporaryDirectory(prefix="cad agent ") as directory:
            pythonpath = os.pathsep.join(filter(None, [str(ROOT / "src"), os.environ.get("PYTHONPATH")]))
            server = StdioServerParameters(command=sys.executable, args=["-m", "consumer_cad_ai.server"],
                                          cwd=directory,
                                          env=dict(os.environ, CAD_WORKSPACE=directory, PYTHONPATH=pythonpath))
            async with stdio_client(server) as (reader, writer):
                async with ClientSession(reader, writer, read_timeout_seconds=timedelta(minutes=3)) as session:
                    await session.initialize()
                    listed = {tool.name for tool in (await session.list_tools()).tools}
                    required = {"enclosure_defaults", "check_enclosure", "build_enclosure", "check_custom",
                                "build_custom", "optimize_enclosure_height", "read_run", "preview_run",
                                "read_artifact"}
                    self.assertTrue(required <= listed, required - listed)

                    defaults = await self.json_tool(session, "enclosure_defaults")
                    bad = defaults | {"battery_thickness": 12}
                    check = await self.json_tool(session, "check_enclosure", parameters=bad)
                    self.assertFalse(check["passed"])
                    self.assertIn("interference", {issue["code"] for issue in check["issues"]})
                    repaired = await self.json_tool(session, "optimize_enclosure_height", parameters=bad,
                                                    min_height=12, max_height=22, step=0.5)
                    self.assertTrue(repaired["passed"])
                    self.assertGreater(repaired["design"]["height"], bad["height"])
                    confirmation = await self.json_tool(session, "check_enclosure", parameters=repaired["design"])
                    self.assertTrue(confirmation["passed"])

                    spec = json.loads((ROOT / "examples/sensor-clip.json").read_text(encoding="utf-8"))
                    self.assertTrue((await self.json_tool(session, "check_custom", spec=spec))["passed"])
                    built = await self.json_tool(session, "build_custom", spec=spec, freecad=False)
                    self.assertTrue(built["passed"], built)
                    run_id = built["run_id"]
                    receipt = await self.json_tool(session, "read_run", run_id=run_id)
                    self.assertTrue(receipt["passed"])
                    self.assertEqual(receipt["artifacts"], built["artifacts"])

                    thumbnail = await session.call_tool("preview_run", {"run_id": run_id})
                    self.assertFalse(thumbnail.isError, str(thumbnail.content)[:200])
                    picture = next(item for item in thumbnail.content if isinstance(item, ImageContent))
                    self.assertEqual(picture.mimeType, "image/png")
                    self.assertTrue(base64.b64decode(picture.data, validate=True).startswith(b"\x89PNG\r\n\x1a\n"))

                    document = bytearray()
                    while True:
                        chunk = await self.json_tool(session, "read_artifact", run_id=run_id,
                                                     artifact="drawing_pdf", offset=len(document))
                        self.assertEqual(chunk["offset"], len(document))
                        document.extend(base64.b64decode(chunk["base64"], validate=True))
                        if chunk["next_offset"] is None:
                            break
                        self.assertGreater(chunk["next_offset"], chunk["offset"])
                        self.assertEqual(chunk["next_offset"], len(document))
                    self.assertEqual(len(document), chunk["total_bytes"])
                    self.assertTrue(document.startswith(b"%PDF-"))
                    self.assertTrue(document.rstrip().endswith(b"%%EOF"))

                    for name, args in (("read_run", {"run_id": "../"}),
                                       ("read_artifact", {"run_id": run_id, "artifact": "../"})):
                        rejected = await session.call_tool(name, args)
                        self.assertTrue(rejected.isError, f"{name} should reject non-identifiers")
