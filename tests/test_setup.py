import importlib.util
import json
import os
from pathlib import Path
import tempfile
import tomllib
import subprocess
import sys
import unittest
from unittest.mock import patch


FILE = Path(__file__).resolve().parents[1] / "scripts" / "configure_agent.py"
SPEC = importlib.util.spec_from_file_location("cad_setup", FILE)
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    def test_configuration_preserves_other_servers_and_paths(self):
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
            skill.write_text("sample")
            cfg = root / ".codex/config.toml"
            cfg.parent.mkdir()
            cfg.write_text('[mcp_servers.other]\ncommand = "other"\n')
            with patch.dict(os.environ, {"FREECAD_CMD": str(freecad)}):
                stdio = setup.configure(root)
                first = cfg.read_text(encoding="utf-8")
                setup.configure(root)
            self.assertEqual(first, cfg.read_text(encoding="utf-8"))
            parsed = tomllib.loads(first)["mcp_servers"]
            self.assertEqual(parsed["other"], {"command": "other"})
            srv = json.loads(stdio.read_text(encoding="utf-8"))["mcpServers"]["consumer-cad"]
            self.assertEqual(parsed["consumer-cad"]["command"], srv["command"])
            self.assertEqual(srv["command"], str(command))
            self.assertEqual(parsed["consumer-cad"]["env"], srv["env"])
            self.assertEqual(srv["env"], {"CAD_WORKSPACE": str(root / "workspace"),
                                          "FREECAD_CMD": str(freecad)})
            self.assertEqual((root / ".agents/skills/consumer-cad/SKILL.md").read_text(), "sample")

    def test_process_scoped_launcher_uses_generated_paths(self):
        launcher_spec = importlib.util.spec_from_file_location("start_codex", FILE.with_name("start_codex.py"))
        launcher = importlib.util.module_from_spec(launcher_spec)
        launcher_spec.loader.exec_module(launcher)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "设计 & CAD"
            (root / ".local").mkdir(parents=True)
            command = str(root / "cad mcp")
            payload = {"command": command, "env": {"CAD_WORKSPACE": str(root / "workspace"), "FREECAD_CMD": "C:\\Apps\\FreeCAD Cmd.exe"}}
            (root / ".local/mcp.json").write_text(json.dumps({"mcpServers": {"consumer-cad": payload}}))
            with patch.object(launcher, "codex_command", return_value=["codex"]), patch.object(subprocess, "call", return_value=0) as proc:
                self.assertEqual(launcher.launch(root, ["mcp", "list"]), 0)
            argv = proc.call_args.args[0]
            self.assertEqual(argv[:4], ["codex", "-C", str(root), "-c"])
            config = tomllib.loads(argv[4])["mcp_servers"]["consumer-cad"]
            self.assertEqual(config["command"], command)
            self.assertEqual(config["env"], payload["env"])
            self.assertEqual(argv[5:], ["mcp", "list"])
            self.assertEqual(proc.call_args.kwargs["cwd"], root)

    def test_native_windows_cli_discovery_is_checkout_scoped(self):
        spec = importlib.util.spec_from_file_location("start_codex", FILE.with_name("start_codex.py"))
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        with tempfile.TemporaryDirectory() as temp, patch.object(sys, "platform", "win32"):
            root = Path(temp) / "cad & models"
            private = root / ".local/codex/codex-x86_64-pc-windows-msvc.exe"
            private.parent.mkdir(parents=True)
            with patch.object(launcher.shutil, "which", return_value="installed-codex.exe"):
                self.assertEqual(launcher.codex_command(root), ["installed-codex.exe"])
                private.touch()
                self.assertEqual(launcher.codex_command(root), [str(private)])

    def test_configuration_respects_user_managed_server(self):
        with self.assertRaisesRegex(ValueError, "user-managed"):
            setup.codex_config('[mcp_servers.consumer-cad]\ncommand = "custom"\n', {})
