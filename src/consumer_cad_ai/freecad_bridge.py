"""Create and reopen a FreeCAD document in a separate, native FreeCAD process."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def _bundled_freecad():
    """Return the bundled FreeCAD console executable when running from a portable bundle."""
    exe = Path(sys.executable).resolve()
    if len(exe.parents) >= 2 and exe.parent.name.lower() == "python" and exe.parents[1].name.lower() == "runtime":
        freecad_bin = exe.parents[1] / "freecad" / "bin"
        for name in ("freecadcmd.exe", "FreeCADCmd.exe"):
            candidate = freecad_bin / name
            if candidate.is_file():
                return candidate
    return None


def find_freecad(command=None):
    """Locate the console executable used by the official Windows and Linux packages."""
    explicit = command or os.environ.get("FREECAD_CMD")
    if explicit:
        path = shutil.which(str(explicit))
        if not path:
            raise FileNotFoundError(f"FreeCAD console executable not found: {explicit}")
        return path
    if bundled := _bundled_freecad():
        return str(bundled)
    for name in ("FreeCADCmd", "freecadcmd", "freecadcmd-python3"):
        if path := shutil.which(name):
            return path
    if os.name == "nt":
        roots = [Path(os.environ[k]) for k in ("ProgramFiles", "LOCALAPPDATA") if k in os.environ]
        if "LOCALAPPDATA" in os.environ:
            roots.append(Path(os.environ["LOCALAPPDATA"]) / "Programs")
        for root in roots:
            for path in sorted(root.glob("FreeCAD*/bin/FreeCADCmd.exe"), reverse=True):
                if path.is_file():
                    return str(path)
    raise FileNotFoundError("Install FreeCAD 0.21 or later, or set FREECAD_CMD to FreeCADCmd.")


def write_fcstd(directory, rows, parameters, hinge, command=None):
    executable = find_freecad(command)
    directory = Path(directory).resolve()
    with tempfile.TemporaryDirectory(prefix="consumer-cad-freecad-") as tmp:
        work = Path(tmp)
        target = work / "assembly.FCStd"
        job = {
            "rows": rows, "parts_root": str(directory), "parameters": parameters,
            "hinge": hinge, "target": str(target), "receipt": str(work / "receipt.json"),
        }
        job_file = work / "job.json"
        job_file.write_text(json.dumps(job), encoding="utf-8")
        env = dict(os.environ)
        for var in ("PYTHONHOME", "PYTHONPATH"):
            env.pop(var, None)
        if sys.platform.startswith("linux") and (
            Path(executable).parent == Path("/usr/bin") or
            Path(executable).resolve().is_relative_to("/usr/lib")
        ):
            # A distro FreeCAD embeds the system Python. setup-python and Conda
            # can inject a different libpython with the same SONAME but different
            # built-in modules (e.g. math). Keep the override local to this child.
            env.pop("LD_LIBRARY_PATH", None)
            env.pop("VIRTUAL_ENV", None)
            env["PYTHONHOME"] = "/usr"
            env["PYTHONNOUSERSITE"] = "1"
            env["PATH"] = os.pathsep.join(["/usr/bin", "/bin", env.get("PATH", "")])
        env.update(CAD_EXPORT_JOB=str(job_file),
                   CAD_EXPORT_SCRIPT=str(Path(__file__).with_name("freecad_worker.py").resolve()))
        launch = "import os, runpy; runpy.run_path(os.environ['CAD_EXPORT_SCRIPT'], run_name='__main__')\n"
        result = subprocess.run(
            [executable, "-c", "-u", str(work / "user.cfg"), "-s", str(work / "system.cfg")],
            input=launch.encode("ascii"), capture_output=True, timeout=180, env=env,
        )
        receipt_file = Path(job["receipt"])
        if result.returncode or not receipt_file.exists() or not target.is_file():
            details = (result.stdout + result.stderr).decode(errors="replace")[-4000:]
            raise RuntimeError(f"FreeCAD document export failed ({result.returncode}): {details}")
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
        if receipt["components"] != len(rows):
            raise RuntimeError(f"FreeCAD component round trip failed: {receipt}")
        shutil.copyfile(target, directory / target.name)
        return target.name
