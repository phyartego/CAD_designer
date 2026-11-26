"""Build and verify a universal Windows x64 portable release ZIP from a committed source tree."""

import argparse
import hashlib
from importlib.metadata import distributions
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import tomllib
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
CACHE = DIST / "cache"
PYTHON_RELEASE = "https://www.python.org/ftp/python/3.12.10"
FREECAD_RELEASE = "https://github.com/FreeCAD/FreeCAD/releases/download/1.1.2"
FREECAD_ARCHIVE = "FreeCAD_1.1.2-Windows-x86_64-py311"
FREECAD_SOURCE = "freecad_source_1.1.2.tar.gz"


def run(*arguments, cwd=ROOT, env=None, capture=False):
    result = subprocess.run(arguments, cwd=cwd, env=env, timeout=600,
                            capture_output=capture, text=capture, encoding="utf-8" if capture else None)
    if result.returncode and capture:
        print(result.stdout + result.stderr, file=sys.stderr)
    result.check_returncode()
    return result


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(name, url, digest):
    path = CACHE / name
    if path.is_file() and sha256(path) == digest:
        return path
    with tempfile.TemporaryDirectory(dir=CACHE) as temporary:
        incoming = Path(temporary) / name
        run("curl.exe", "--fail", "--location", "--silent", "--show-error", "--retry", "2",
            "--output", incoming, url)
        if sha256(incoming) != digest:
            raise RuntimeError(f"SHA-256 mismatch for {url}")
        incoming.replace(path)
    return path


def add_runtimes(bundle, work, seven_zip):
    runtime = bundle / "runtime"
    python = download("python-3.12.10.zip", f"{PYTHON_RELEASE}/python-3.12.10-embed-amd64.zip",
                      "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3")
    with ZipFile(python) as archive:
        archive.extractall(runtime / "python")
    (runtime / "python" / "python312._pth").write_text(
        "python312.zip\n.\n../../scripts\nimport site\n", encoding="ascii")

    freecad = download("freecad-1.1.2.7z", f"{FREECAD_RELEASE}/{FREECAD_ARCHIVE}.7z",
                       "76d848d5a8baad129e2700ef53bd08525c3063ea14036edffef6b41b9eaab5ef")
    run(seven_zip, "x", "-y", "-bb0", "-bso0", f"-o{work}", freecad)
    (work / FREECAD_ARCHIVE).rename(runtime / "freecad")
    # Native Python wheels also load the app-local MSVC C++ runtime.
    for pattern in ("msvcp140*.dll", "concrt140.dll", "vcruntime140_threads.dll"):
        for dll in (runtime / "freecad" / "bin").glob(pattern):
            shutil.copy2(dll, runtime / "python")


def verify(archive, work, seven_zip, full_tests):
    print("Extracting the finished ZIP for verification.", flush=True)
    extraction = work / "Relocated CAD"
    run(seven_zip, "x", "-y", "-bb0", "-bso0", f"-o{extraction}", archive)
    bundle = extraction / archive.stem
    env = os.environ.copy()
    system = Path(os.environ["SystemRoot"])
    env.update(PATH=os.pathsep.join([str(system / "System32"), str(system)]),
               MPLCONFIGDIR=str(work / "matplotlib"))
    for var in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "FREECAD_CMD", "CAD_WORKSPACE"):
        env.pop(var, None)

    doctor_out = run("cmd.exe", "/d", "/c", "cad.cmd", "doctor", cwd=bundle, env=env, capture=True)
    doctor = json.loads(doctor_out.stdout)
    if not doctor["passed"] or not Path(doctor["freecad_console"]).resolve().is_relative_to(
        (bundle / "runtime" / "freecad").resolve()
    ):
        raise RuntimeError(f"Bundled doctor check failed: {doctor}")

    run("cmd.exe", "/d", "/c", "Run-Demo.cmd", "--no-open", cwd=bundle, env=env)
    manifest_file, = (bundle / "outputs").glob("desktop-stand-*/manifest.json")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    expected = {"assembly.FCStd", "assembly.step", "assembly.pdf", "assembly.dxf",
                "bom.csv", "preview.png", "verification.json", "recipe.py"}
    if not manifest["passed"] or not expected <= {p.name for p in manifest_file.parent.iterdir()}:
        raise RuntimeError("The bundled desktop stand demo did not generate the expected deliverables")

    run("cmd.exe", "/d", "/c", "Setup-Agent.cmd", "--no-pause", "--no-copy", cwd=bundle, env=env)
    root_mcp = bundle / "mcp.json"
    dot_mcp = bundle / ".mcp.json"
    if not root_mcp.is_file() or not dot_mcp.is_file():
        raise RuntimeError("Setup-Agent.cmd did not generate mcp.json and .mcp.json")
    server = json.loads(root_mcp.read_text(encoding="utf-8"))["mcpServers"]["consumer-cad"]
    python = bundle / "runtime/python/python.exe"
    if (server.get("type") != "stdio" or Path(server["command"]) != python
            or server["args"] != ["-m", "consumer_cad_ai", "serve"]
            or Path(server["env"]["CAD_WORKSPACE"]).resolve() != (bundle / "workspace").resolve()
            or not Path(server["env"]["FREECAD_CMD"]).resolve().is_relative_to((bundle / "runtime/freecad").resolve())):
        raise RuntimeError(f"Setup-Agent.cmd wrote unexpected MCP config: {server}")

    mcp_probe = """
import asyncio, json, os, pathlib
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

bundle = pathlib.Path(os.environ["BUNDLE"]).resolve()
cfg = json.loads((bundle / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]["consumer-cad"]
expected_tools = {
    "enclosure_defaults", "check_enclosure", "optimize_enclosure_height", "build_enclosure",
    "solid_schema", "check_custom", "build_custom", "read_run", "preview_run", "read_artifact",
}

async def check_server(srv_env, test_build):
    params = StdioServerParameters(command=cfg["command"], args=cfg["args"], cwd=str(bundle), env=srv_env)
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            assert expected_tools <= tools, expected_tools - tools
            res = await session.call_tool("enclosure_defaults", {})
            assert not res.isError
            if test_build:
                spec = json.loads((bundle / "examples/sensor-clip.json").read_text(encoding="utf-8"))
                built = await session.call_tool("build_custom", {"spec": spec, "freecad": True})
                assert not built.isError, built.content
                payload = built.structuredContent or json.loads(built.content[0].text)
                assert payload["passed"], payload
                run_dir = bundle / "workspace" / payload["run_id"]
                assert (run_dir / "assembly.FCStd").is_file(), f"Missing FCStd in {run_dir}"

async def main():
    base = {k: os.environ[k] for k in ("SystemRoot", "PATH", "MPLCONFIGDIR") if k in os.environ}
    await check_server(base | cfg["env"], test_build=False)
    await check_server(base, test_build=True)

asyncio.run(main())
"""
    probe_env = env | {"BUNDLE": str(bundle)}
    run(python, "-c", mcp_probe, cwd=bundle, env=probe_env)

    tests = ["discover", "-s", "tests"] if full_tests else ["discover", "-s", "tests", "-p", "test_agent.py"]
    run(python, "-m", "unittest", *tests, "-v", cwd=bundle, env=env)


def build(ref, seven_zip, full_tests):
    commit = run("git", "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}",
                 capture=True).stdout.strip()
    CACHE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="portable-", dir=DIST) as temporary:
        work = Path(temporary)
        tree = work / "source.zip"
        source = work / "source"
        run("git", "archive", "--format=zip", f"--output={tree}", commit)
        with ZipFile(tree) as archive:
            archive.extractall(source)
        version = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
        bundle = work / f"Consumer-CAD-AI-v{version}-Windows-x64-Portable"
        with ZipFile(tree) as archive:
            archive.extractall(bundle)
        for file in (bundle / "scripts/portable").iterdir():
            encoding = "ascii" if file.suffix == ".cmd" else "utf-8-sig"
            (bundle / file.name).write_text(file.read_text(encoding="utf-8"), encoding=encoding)
        for name in ("Setup-Agent", "Run-Demo", "Open-FreeCAD", "cad", "cad-mcp"):
            if not (bundle / f"{name}.cmd").is_file():
                raise RuntimeError(f"Missing committed portable launcher {name}.cmd")
        skill_src = bundle / "skills/consumer-cad/SKILL.md"
        skill_dst = bundle / ".agents/skills/consumer-cad/SKILL.md"
        skill_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(skill_src, skill_dst)

        print(f"Bundling Windows runtimes for {commit}.", flush=True)
        add_runtimes(bundle, work, seven_zip)
        wheels = work / "wheels"
        run(sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", wheels, source)
        packages = bundle / "runtime/python/Lib/site-packages"
        wheel, = wheels.glob("consumer_cad_ai-*.whl")
        run(sys.executable, "-m", "pip", "install", "--only-binary=:all:", "--no-compile",
            "--target", packages, wheel)
        metadata, = packages.glob("consumer_cad_ai-*.dist-info")
        (metadata / "direct_url.json").unlink(missing_ok=True)
        # pip's generated console launchers point to the build interpreter.
        for dirname in ("bin", "Scripts"):
            folder = packages / dirname
            if folder.is_dir() and folder.resolve().is_relative_to(bundle.resolve()):
                shutil.rmtree(folder)
        inventory = sorted(f"{package.metadata['Name']}=={package.version}"
                           for package in distributions(path=[str(packages)]))
        (bundle / "python-packages.txt").write_text("\n".join(inventory) + "\n", encoding="utf-8")
        (bundle / "source-commit.txt").write_text(commit + "\n", encoding="ascii")

        archive = work / (bundle.name + ".zip")
        print(f"Compressing {archive.name}.", flush=True)
        run(seven_zip, "a", "-tzip", "-mm=Deflate", "-mx=3", "-mcu=on", "-bb0", "-bso0",
            archive, bundle.name, cwd=work)
        if archive.stat().st_size >= 2**31:
            raise RuntimeError("The ZIP exceeds GitHub's per-asset limit")
        verify(archive, work, seven_zip, full_tests)

        freecad_source = download("freecad-source-1.1.2.tar.gz", f"{FREECAD_RELEASE}/{FREECAD_SOURCE}",
                                  "c4f67a2fbbb8e1c5cabf266706816f3f9b39ee2d75296d2858a54ed5a0be99ea")
        shutil.copyfile(freecad_source, DIST / FREECAD_SOURCE)
        final = DIST / archive.name
        digest = sha256(archive)
        archive.replace(final)
        final.with_suffix(".zip.sha256").write_text(f"{digest}  {final.name}\n", encoding="ascii")
        print(f"{final} ({final.stat().st_size / 2**20:.1f} MiB)\nSHA-256 {digest}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD", help="git commit, tag or branch to pack")
    parser.add_argument("--seven-zip", default=shutil.which("7z"), help="path to the 7z executable")
    parser.add_argument("--full-tests", action="store_true", help="run all tests after extracting the ZIP")
    options = parser.parse_args()
    if platform.system() != "Windows" or platform.machine().upper() not in {"AMD64", "X86_64"} or (
        sys.version_info[:2] != (3, 12) or sys.maxsize <= 2**32
    ):
        parser.error("Build from Windows x64 using 64-bit Python 3.12 with pip")
    if not options.seven_zip:
        parser.error("Install 7-Zip or provide --seven-zip")
    build(options.ref, options.seven_zip, options.full_tests)
