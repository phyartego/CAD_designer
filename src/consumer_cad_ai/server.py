"""MCP entry point for parameterized modelling and artifact inspection."""

import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from uuid import uuid4

import anyio
from mcp.server.fastmcp import FastMCP, Image

from .design import Design

_CHUNK = 48 * 1024


async def _cad(operation, data=None, args=()):
    """Keep the native CAD runtime off the MCP transport's stdin/stdout and event loop."""
    with tempfile.TemporaryDirectory(prefix="cad-worker-") as work:
        directory = Path(work)
        result_file = directory / "report.json"
        command = [sys.executable, "-m", "consumer_cad_ai", "--json-out", str(result_file), operation]
        if data is not None:
            input_file = directory / "input.json"
            input_file.write_text(json.dumps(data, allow_nan=False), encoding="utf-8")
            command.append(str(input_file))
        process = await anyio.run_process(
            [*command, *args], stdin=subprocess.DEVNULL, check=False,
        )
        if process.returncode not in (0, 2) or not result_file.is_file():
            detail = (process.stderr or process.stdout or b"").decode(errors="replace")[-2500:]
            raise RuntimeError(f"CAD {operation} failed (exit {process.returncode}): {detail}")
        return json.loads(result_file.read_text(encoding="utf-8"))


def _workspace():
    configured = os.environ.get("CAD_WORKSPACE")
    return Path(configured or Path.home() / "consumer-cad-workspace").expanduser().resolve()


def _run_directory(run_id):
    if not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise ValueError("Use the run_id returned by a build tool")
    root = _workspace()
    directory = root / run_id
    if directory.is_symlink() or not (directory / "manifest.json").is_file():
        raise ValueError("Unknown or unfinished design run")
    return directory


def _manifest(run_id):
    directory = _run_directory(run_id)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    return {**manifest, "run_id": run_id}


def _artifact_path(run_id, artifact):
    directory = _run_directory(run_id)
    paths = _manifest(run_id)["artifacts"]
    if artifact in paths:
        path = directory / paths[artifact]
    elif "parts" in paths and re.fullmatch(r"parts/[\w-]+\.step", artifact, re.ASCII):
        path = directory / artifact
    else:
        raise ValueError("Use an artifact key from the manifest or a parts/*.step entry in the BOM")
    if not path.resolve().is_relative_to(directory) or not path.is_file():
        raise ValueError("Artifact is not an available file")
    return path


def create_server(**settings):
    server = FastMCP(
        "consumer-cad",
        instructions="All geometry uses millimetres. Inspect verification before publishing a design. "
                     "Call enclosure_defaults for the hinged compartment or solid_schema for a custom assembly. "
                     "Build tools create a new immutable run. Use preview_run and read_artifact for outputs.",
        **settings,
    )

    worker_slot = anyio.CapacityLimiter(1)

    async def execute(operation, data=None, args=()):
        async with worker_slot:
            return await _cad(operation, data, args)

    async def publish(operation, data, freecad):
        run_id = uuid4().hex
        args = ["--out", str(_workspace() / run_id)]
        if freecad is not None:
            args.append("--freecad" if freecad else "--no-freecad")
        receipt = await execute(operation, data, args)
        return {**receipt, "run_id": run_id}

    @server.tool()
    def enclosure_defaults() -> dict:
        """Return editable millimetre/degree parameters for the hinged metal battery enclosure."""
        return Design().to_dict()

    @server.tool()
    async def check_enclosure(parameters: dict) -> dict:
        """Measure solids, clearances, pairwise interference and sampled hinge poses. Accepts partial overrides."""
        return await execute("check", parameters)

    @server.tool()
    async def optimize_enclosure_height(parameters: dict, min_height: float,
                                        max_height: float, step: float = 0.5) -> dict:
        """Find a verified compact body height on the requested mm grid, preserving PCB and cell dimensions."""
        return await execute("optimize", parameters, ["--min-height", str(min_height),
                                                  "--max-height", str(max_height), "--step", str(step)])

    @server.tool()
    async def build_enclosure(parameters: dict, freecad: bool | None = None) -> dict:
        """Verify and export the parametric enclosure. True requires FCStd, null auto-detects FreeCAD."""
        return await publish("build", parameters, freecad)

    @server.tool()
    async def solid_schema() -> dict:
        """Return the JSON specification for arbitrary multi-part box/cylinder CAD models and hinge motion."""
        return await execute("schema")

    @server.tool()
    async def check_custom(spec: dict) -> dict:
        """Measure and check a declarative solid model as defined in solid_schema, without writing files."""
        return await execute("check-spec", spec)

    @server.tool()
    async def build_custom(spec: dict, freecad: bool | None = None) -> dict:
        """Verify and export a declarative assembly. Revise the JSON spec to iterate on new product geometry."""
        return await publish("build-spec", spec, freecad)

    @server.tool()
    def read_run(run_id: str) -> dict:
        """Retrieve a completed run's measurements, issues and artifact paths from its permanent receipt."""
        return _manifest(run_id)

    @server.tool()
    def preview_run(run_id: str) -> Image:
        """Return the exported general-arrangement drawing as an actual PNG image."""
        return Image(path=str(_artifact_path(run_id, "preview")), format="png")

    @server.tool()
    def read_artifact(run_id: str, artifact: str, offset: int = 0) -> dict:
        """Read one binary chunk by artifact key or a BOM parts/*.step path. Follow next_offset until null."""
        path = _artifact_path(run_id, artifact)
        total = path.stat().st_size
        if not 0 <= offset <= total:
            raise ValueError("Offset lies outside the artifact")
        with path.open("rb") as stream:
            stream.seek(offset)
            chunk = stream.read(_CHUNK)
        end = offset + len(chunk)
        return {"name": path.name, "offset": offset, "total_bytes": total,
                "next_offset": end if end < total else None,
                "base64": base64.b64encode(chunk).decode("ascii")}

    return server


def main():
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
