import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from consumer_cad_ai import freecad_bridge, server


FILE = Path(__file__).resolve().parents[1] / "scripts" / "configure_agent.py"
SPEC = importlib.util.spec_from_file_location("cad_setup", FILE)
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    def test_source_checkout_configuration_writes_universal_mcp_and_skill(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve() / "含 空格"
            folder = "Scripts" if os.name == "nt" else "bin"
            launcher = "consumer-cad-mcp.exe" if os.name == "nt" else "consumer-cad-mcp"
            command = root / ".venv" / folder / launcher
            command.parent.mkdir(parents=True)
            command.touch()
            freecad = root / "FreeCAD cmd"
            freecad.touch()
            skill = root / "skills/consumer-cad/SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("sample", encoding="utf-8")

            with patch.dict(os.environ, {"FREECAD_CMD": str(freecad)}):
                primary = setup.configure(root)
                first = primary.read_text(encoding="utf-8")
                setup.configure(root)

            self.assertEqual(primary, root / ".local" / "mcp.json")
            self.assertFalse((root / "mcp.json").exists())
            self.assertEqual(first, (root / ".mcp.json").read_text(encoding="utf-8"))
            srv = json.loads(first)["mcpServers"]["consumer-cad"]
            self.assertEqual(srv["type"], "stdio")
            self.assertEqual(srv["command"], str(command))
            self.assertEqual(srv["args"], [])
            self.assertEqual(srv["env"], {"CAD_WORKSPACE": str(root / "workspace"),
                                          "FREECAD_CMD": str(freecad)})
            self.assertEqual((root / ".agents/skills/consumer-cad/SKILL.md").read_text(encoding="utf-8"), "sample")

    def test_portable_bundle_configuration_writes_root_and_workspace_mcp(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve() / "便携 目录"
            py = root / "runtime" / "python" / "python.exe"
            fc = root / "runtime" / "freecad" / "bin" / "freecadcmd.exe"
            py.parent.mkdir(parents=True)
            fc.parent.mkdir(parents=True)
            py.touch()
            fc.touch()
            skill = root / "skills/consumer-cad/SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("portable-skill", encoding="utf-8")

            primary = setup.configure(root)
            self.assertEqual(primary, root / "mcp.json")
            self.assertTrue((root / ".mcp.json").is_file())
            self.assertEqual(primary.read_text(encoding="utf-8"),
                             (root / ".mcp.json").read_text(encoding="utf-8"))
            srv = json.loads(primary.read_text(encoding="utf-8"))["mcpServers"]["consumer-cad"]
            self.assertEqual(srv["type"], "stdio")
            self.assertEqual(srv["command"], str(py))
            self.assertEqual(srv["args"], ["-m", "consumer_cad_ai", "serve"])
            self.assertEqual(srv["env"], {"CAD_WORKSPACE": str(root / "workspace"),
                                          "FREECAD_CMD": str(fc)})
            self.assertEqual((root / ".agents/skills/consumer-cad/SKILL.md").read_text(encoding="utf-8"),
                             "portable-skill")

    def test_portable_zero_env_autodiscovery(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve() / "CAD 便携"
            py = root / "runtime" / "python" / "python.exe"
            fc = root / "runtime" / "freecad" / "bin" / "freecadcmd.exe"
            py.parent.mkdir(parents=True)
            fc.parent.mkdir(parents=True)
            py.touch()
            fc.touch()

            with patch.object(sys, "executable", str(py)):
                with patch.dict(os.environ, {}, clear=True):
                    self.assertEqual(Path(freecad_bridge.find_freecad()).resolve(), fc)
                    self.assertEqual(server._workspace(), (root / "workspace").resolve())
                override_ws = str(root / "custom-ws")
                with patch.dict(os.environ, {"CAD_WORKSPACE": override_ws}, clear=True):
                    self.assertEqual(server._workspace(), Path(override_ws).resolve())
