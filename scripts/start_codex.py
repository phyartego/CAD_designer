"""Launch Codex for this checkout with an explicit, process-scoped MCP server."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def codex_command(root=None):
    root = Path(__file__).resolve().parents[1] if root is None else root
    private = root / ".local" / "codex" / "codex-x86_64-pc-windows-msvc.exe"
    if sys.platform == "win32" and private.is_file():
        return [str(private)]
    cli = shutil.which("codex")
    if not cli:
        raise RuntimeError("Run scripts/install.ps1 on Windows, install Codex CLI, or use .local/mcp.json with your stdio client")
    if os.name == "nt" and Path(cli).suffix.lower() in (".cmd", ".bat", ".ps1"):
        # Invoke npm's executable JS entry point directly. cmd.exe re-parses TOML
        # quotes and characters in file names, even when Python passes an argv list.
        entry = Path(cli).parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
        node = shutil.which("node")
        if not node or not entry.is_file():
            raise RuntimeError("Use the native Codex executable or the official @openai/codex npm installation")
        return [node, str(entry)]
    return [cli]


def launch(root, arguments):
    file = root / ".local" / "mcp.json"
    if not file.exists():
        raise RuntimeError("Run the installation script first to generate .local/mcp.json")
    server = json.loads(file.read_text(encoding="utf-8"))["mcpServers"]["consumer-cad"]
    quote = lambda value: json.dumps(value, ensure_ascii=False)
    env = ", ".join(f"{quote(key)}={quote(value)}" for key, value in server["env"].items())
    override = ("mcp_servers.consumer-cad={command=" + quote(server["command"]) +
                ", startup_timeout_sec=90, tool_timeout_sec=600, env={" + env + "}}")
    return subprocess.call([*codex_command(root), "-C", str(root), "-c", override, *arguments], cwd=root)


if __name__ == "__main__":
    try:
        raise SystemExit(launch(Path(__file__).resolve().parents[1], sys.argv[1:]))
    except (OSError, RuntimeError) as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)
