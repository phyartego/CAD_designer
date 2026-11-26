"""Build and verify a Windows x64 release ZIP from a committed source tree."""

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
CODEX_TAG = "rust-v0.170.0"
CODEX_EXE = "codex-x86_64-pc-windows-msvc.exe"
CODEX_RELEASE = f"https://github.com/openai/codex/releases/download/{CODEX_TAG}"
CODEX_SOURCE = f"https://raw.githubusercontent.com/openai/codex/{CODEX_TAG}"


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

    codex = download("codex-0.170.0.zip", f"{CODEX_RELEASE}/{CODEX_EXE}.zip",
                     "b1634415b6ecb87fea80691580dfe49f83fd46f0ad93f128ba029604d7faa158")
    with ZipFile(codex) as archive:
        archive.extractall(runtime / "codex")
    for name, digest in {
        "LICENSE": "d17f227e4df5da1600391338865ce0f3055211760a36688f816941d58232d8dc",
        "NOTICE": "9d71575ecfd9a843fc1677b0efb08053c6ba9fd686a0de1a6f5382fd3c220915",
    }.items():
        shutil.copyfile(download(f"codex-{name}", f"{CODEX_SOURCE}/{name}", digest),
                        runtime / "codex" / name)


def verify(archive, work, seven_zip, full_tests):
    print("Extracting the finished ZIP for verification.", flush=True)
    extraction = work / "Relocated CAD"
    run(seven_zip, "x", "-y", "-bb0", "-bso0", f"-o{extraction}", archive)
    bundle = extraction / archive.stem
    env = os.environ.copy()
    system = Path(os.environ["SystemRoot"])
    env.update(PATH=os.pathsep.join([str(system / "System32"), str(system)]),
               CODEX_HOME=str(work / "codex-test-home"),
               MPLCONFIGDIR=str(work / "matplotlib"),
               FREECAD_CMD=str(bundle / "runtime/freecad/bin/freecadcmd.exe"))
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    env.pop("VIRTUAL_ENV", None)

    run("cmd.exe", "/d", "/c", "cad.cmd", "doctor", cwd=bundle, env=env)
    run("cmd.exe", "/d", "/c", "Run-Demo.cmd", "--no-open", cwd=bundle, env=env)
    manifest_file, = (bundle / "outputs").glob("*/manifest.json")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    expected = {"assembly.FCStd", "assembly.step", "assembly.pdf",
                "assembly.dxf", "bom.csv", "preview.png", "verification.json"}
    if not manifest["passed"] or not expected <= {p.name for p in manifest_file.parent.iterdir()}:
        raise RuntimeError("The bundled demo did not generate the expected deliverables")

    listing = run("cmd.exe", "/d", "/c", "Start-Codex.cmd", "mcp", "get", "consumer-cad", "--json",
                  cwd=bundle, env=env, capture=True)
    server = json.loads(listing.stdout)
    python = bundle / "runtime/python/python.exe"
    if (not server["enabled"] or Path(server["transport"]["command"]) != python
            or server["transport"]["args"] != ["-m", "consumer_cad_ai", "serve"]):
        raise RuntimeError(f"Codex did not register the bundled MCP server: {server}")
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
        for name in ("Start-Codex", "Run-Demo", "Open-FreeCAD", "cad"):
            if not (bundle / f"{name}.cmd").is_file():
                raise RuntimeError(f"Missing committed portable launcher {name}.cmd")

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
