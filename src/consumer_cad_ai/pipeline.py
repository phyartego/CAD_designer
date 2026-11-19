"""Build, verify and publish a complete design run to a new local directory."""

import ctypes
import errno
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from . import geometry
from .design import Design
from .exports import export_design
from .freecad_bridge import find_freecad
from .recipe import load_recipe


def _publish(source, target):
    """Atomically rename a complete directory without replacing a competing result."""
    if sys.platform.startswith("linux"):
        # Plain POSIX rename() can replace an existing empty directory. Modern Linux
        # exposes a no-replace variant used by both local builds and stdio MCP runs.
        rename = ctypes.CDLL(None, use_errno=True).renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        status = rename(-100, os.fsencode(source), -100, os.fsencode(target), 1)  # AT_FDCWD, RENAME_NOREPLACE
        if status:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), str(target))
    elif sys.platform == "darwin":
        rename = ctypes.CDLL(None, use_errno=True).renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        if rename(os.fsencode(source), os.fsencode(target), 4):  # RENAME_EXCL
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), str(target))
    elif os.name == "nt":
        # Windows os.rename() already fails when the destination exists.
        os.rename(source, target)
    else:
        raise OSError(errno.ENOTSUP, "Atomic no-replace publication is unavailable on this platform")


def _freecad_command(freecad):
    if freecad is False:
        return None
    if freecad is not True and freecad is not None:
        raise ValueError("freecad must be true, false or null")
    try:
        return find_freecad()
    except FileNotFoundError:
        if freecad or os.environ.get("FREECAD_CMD"):
            raise
        return None


def _write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _run(parameters, out, kind, freecad, source=None):
    target = Path(os.path.abspath(out))
    if os.path.lexists(target):
        raise FileExistsError(errno.EEXIST, "Choose a new output directory", str(target))
    if any(parent.is_symlink() for parent in target.parents):
        raise ValueError("Choose an output directory without symlinked parent directories")
    target.parent.mkdir(exist_ok=True, parents=True)
    command = _freecad_command(freecad)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix=".cad-stage-") as work:
        stage = Path(work) / "result"
        stage.mkdir()
        artifacts = {"design": "design.json", "verification": "verification.json", "manifest": "manifest.json"}
        if source is not None:
            if source.suffix.lower() != ".py":
                raise ValueError("A local recipe must be a .py source file")
            shutil.copyfile(source, stage / "recipe.py")
            artifacts["recipe"] = "recipe.py"

        try:
            if kind == "enclosure":
                design = Design.from_dict(parameters)
                parameters = design.to_dict()
                parts = geometry.build_assembly(design)
                hinge = geometry.hinge_axis(design)
                report = geometry.verify(design, parts)
            else:
                if kind == "spec":
                    from .solid_spec import SolidSpec, build_spec
                    parameters = SolidSpec.model_validate(parameters).model_dump(mode="json")
                    parts, hinge, angles = build_spec(parameters)
                else:
                    parts, hinge, angles = load_recipe(stage / "recipe.py", parameters)
                report = geometry.verify_components(parts, hinge, angles)
        except ValueError as exc:
            report = {"passed": False, "issues": [{"code": "invalid_design", "message": str(exc)}]}

        _write_json(stage / "design.json", parameters)
        _write_json(stage / "verification.json", report)
        if report["passed"]:
            artifacts.update(export_design(parts, parameters, stage, freecad=command is not None,
                                           freecad_cmd=command, hinge=hinge))
        result = {"schema_version": 1, "kind": kind, "passed": report["passed"], "output_dir": str(target),
                  "verification": report, "artifacts": artifacts}
        _write_json(stage / "manifest.json", result)
        _publish(stage, target)
        return result


def run_enclosure(parameters: dict, out: Path, freecad: bool | None = None) -> dict:
    """Build a parameterized enclosure in a new output directory."""
    return _run(parameters, out, "enclosure", freecad)


def run_spec(spec: dict, out: Path, freecad: bool | None = None) -> dict:
    """Build a declarative assembly specification in a new output directory."""
    return _run(spec, out, "spec", freecad)


def run_recipe(path: Path, parameters: dict, out: Path, freecad: bool | None = None) -> dict:
    """Execute a trusted, single-file local recipe and archive its exact source bytes."""
    return _run(parameters, out, "recipe", freecad, source=Path(path))
