"""Configure local stdio MCP clients for a source checkout or a Windows portable bundle."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


NAME = "consumer-cad"


def write_text(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == contents:
        return
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                     dir=path.parent, delete=False) as stream:
        tmp = Path(stream.name)
        try:
            stream.write(contents)
            stream.flush()
        except BaseException:
            stream.close()
            tmp.unlink(missing_ok=True)
            raise
    try:
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def is_portable_bundle(root: Path) -> bool:
    return (root / "runtime" / "python" / "python.exe").is_file()


def build_server_config(root: Path) -> dict:
    """Build a universal stdio MCP server definition for the given root directory."""
    root = root.resolve()
    env = {"CAD_WORKSPACE": str(root / "workspace")}
    if is_portable_bundle(root):
        command = root / "runtime" / "python" / "python.exe"
        args = ["-m", "consumer_cad_ai", "serve"]
        freecad = (root / "runtime" / "freecad" / "bin" / "freecadcmd.exe").resolve(strict=True)
        env["FREECAD_CMD"] = str(freecad)
    else:
        bin_dir = root / ".venv" / ("Scripts" if os.name == "nt" else "bin")
        command = bin_dir / ("consumer-cad-mcp.exe" if os.name == "nt" else "consumer-cad-mcp")
        if not command.is_file():
            raise FileNotFoundError(f"Install the project in {root / '.venv'} first")
        args = []
        if os.environ.get("FREECAD_CMD"):
            env["FREECAD_CMD"] = str(Path(os.environ["FREECAD_CMD"]).resolve(strict=True))
    return {"type": "stdio", "command": str(command), "args": args, "env": env}


def configure(root: Path) -> Path:
    """Write standard MCP JSON configuration files and sync the agent skill."""
    root = root.resolve()
    server = build_server_config(root)
    payload = json.dumps({"mcpServers": {NAME: server}}, indent=2, ensure_ascii=False) + "\n"

    portable = is_portable_bundle(root)
    if portable:
        write_text(root / "mcp.json", payload)
    write_text(root / ".mcp.json", payload)
    local_mcp = root / ".local" / "mcp.json"
    write_text(local_mcp, payload)

    skill_src = root / "skills" / NAME / "SKILL.md"
    if skill_src.is_file():
        write_text(root / ".agents" / "skills" / NAME / "SKILL.md",
                   skill_src.read_text(encoding="utf-8"))

    return (root / "mcp.json") if portable else local_mcp


def copy_to_clipboard(text: str) -> bool:
    """Best-effort clipboard copy on Windows without mutating Unicode paths."""
    if sys.platform != "win32":
        return False
    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "[Console]::InputEncoding = [System.Text.Encoding]::UTF8; "
             "$text = [Console]::In.ReadToEnd(); Set-Clipboard -Value $text"],
            input=text.encode("utf-8"),
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def print_guide(root: Path, primary: Path, copied: bool) -> None:
    root = root.resolve()
    data = json.loads(primary.read_text(encoding="utf-8"))
    server = data["mcpServers"][NAME]
    skill_path = root / "skills" / NAME / "SKILL.md"
    print("=" * 68)
    print("Consumer CAD AI — 通用 Agent / MCP 接入向导")
    print("=" * 68)
    print(f"已生成配置文件: {primary}")
    print(f"工作区自动发现: {root / '.mcp.json'}")
    print(f"Agent 技能文件: {skill_path}")
    print(f"设计结果保存至: {server['env']['CAD_WORKSPACE']}")
    if copied:
        print("\n[已自动复制标准 MCP JSON 到剪贴板，可直接粘贴到客户端!]")
    print("\n--- 1. 标准 MCP JSON 配置 (适用于 WorkBuddy / Cursor / Claude / 等) ---")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    print("\n--- 2. WorkBuddy 自定义连接器（若需逐项填写） ---")
    print(f"名称 (Name)     : {NAME}")
    print(f"传输类型 (Type) : {server['type']}")
    print(f"命令 (Command)  : {server['command']}")
    print(f"参数 (Args)     : {' '.join(server['args']) if server['args'] else '(留空)'}")
    print("环境变量 (Env)  :")
    for key, value in server["env"].items():
        print(f"  {key} = {value}")
    print(f"\n建议同时在 WorkBuddy 中导入技能文件:\n  {skill_path}")
    print("=" * 68)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-guide", action="store_true",
                        help="print beginner-friendly Chinese setup instructions")
    parser.add_argument("--copy", action="store_true",
                        help="copy the generated MCP JSON to the Windows clipboard")
    parser.add_argument("--no-copy", action="store_true",
                        help="disable clipboard copy even when --copy is set")
    parser.add_argument("--no-pause", action="store_true",
                        help="accepted for batch wrapper compatibility")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    primary = configure(root)
    copied = False
    if args.copy and not args.no_copy:
        copied = copy_to_clipboard(primary.read_text(encoding="utf-8"))
    if args.print_guide:
        print_guide(root, primary, copied)
    else:
        print("Configured universal MCP and skill. Configuration file:", primary)
