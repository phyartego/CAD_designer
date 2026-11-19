"""Manufacturing exchange, native project, and inspection outputs for one design run."""

import csv
import re
from pathlib import Path

from build123d import Color, Compound, Part, export_step

from .drawings import write_drawings
from .freecad_bridge import write_fcstd


def _step(shape, path):
    if not export_step(shape, str(path)):
        raise RuntimeError(f"STEP export failed for {path.name}")


def export_design(parts, parameters, output_dir, *, freecad=False, freecad_cmd=None, hinge=None):
    """Write one closed assembly to a fresh run directory; return relative artifact paths.

    A component name identifies an installed occurrence. Per-component files retain
    the assembly datum, which makes them easy to overlay or reassemble without transforms.
    """
    parts = list(parts)
    if not parts or len({p.name for p in parts}) != len(parts):
        raise ValueError("Export requires a non-empty assembly and unique component names")
    directory = Path(output_dir)
    part_dir = directory / "parts"
    part_dir.mkdir(parents=True, exist_ok=True)
    palette = {"Aluminium": (0.72, 0.75, 0.78), "Stainless steel": (0.51, 0.55, 0.59),
               "Spring steel": (0.4, 0.42, 0.45), "Polymer": (0.24, 0.27, 0.30),
               "FR-4": (0.12, 0.42, 0.27), "Pouch cell": (0.78, 0.68, 0.39)}
    children = []
    for part in parts:
        # Wrap the geometry afresh so exporting doesn't reparent the source model.
        shape = Compound.cast(part.shape.wrapped)
        if isinstance(shape, Compound):
            solids = shape.solids()
            shape = solids[0] if len(solids) == 1 else Part(shape.wrapped)
        shape.label = part.name
        shape.color = part.shape.color or Color(*palette.get(part.material, (0.65, 0.65, 0.65)))
        children.append(shape)
    assembly = Compound(label="Consumer electronics assembly", children=children)
    _step(assembly, directory / "assembly.step")
    rows = []
    for index, (part, shape) in enumerate(zip(parts, children), start=1):
        slug = re.sub(r"[^A-Za-z0-9_-]+", "_", part.name).strip("_")[:55] or "part"
        step_file = f"parts/{index:03d}_{slug}.step"
        _step(shape, directory / step_file)
        rows.append({"item": index, "name": part.name, "material": part.material,
                     "quantity": 1, "moving": part.moving,
                     "volume_mm3": round(part.shape.volume, 4), "step": step_file})
    with (directory / "bom.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    write_drawings(assembly, parts, directory)
    paths = {"assembly": "assembly.step", "parts": "parts", "drawing_dxf": "assembly.dxf",
             "drawing_pdf": "assembly.pdf", "preview": "preview.png", "bom": "bom.csv"}
    if freecad:
        axis = (tuple(hinge.position), tuple(hinge.direction)) if hinge is not None else None
        paths["freecad"] = write_fcstd(directory, rows, parameters, axis, command=freecad_cmd)
    return paths
