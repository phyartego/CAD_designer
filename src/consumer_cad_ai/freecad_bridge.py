"""Create and reopen a FreeCAD document in a separate, native FreeCAD process."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def find_freecad(command=None):
    """Locate the console executable used by the official Windows and Linux packages."""
    explicit = command or os.environ.get("FREECAD_CMD")
    if explicit:
        path = shutil.which(str(explicit))
        if not path:
            raise FileNotFoundError(f"FreeCAD console executable not found: {explicit}")
        return path
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
    raise FileNotFoundError("Install FreeCAD 1.x or set FREECAD_CMD to FreeCADCmd.")


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
