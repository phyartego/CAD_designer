"""Executed by FreeCADCmd. Only import modules available in FreeCAD's own Python."""

import json
import os
from pathlib import Path


def create_document(job):
    import FreeCAD as App
    import Part

    doc = App.newDocument("ConsumerCAD")
    assembly = doc.addObject("App::Part", "Assembly")
    assembly.Label = "Consumer electronics assembly"
    assembly.addProperty("App::PropertyString", "DesignJSON", "Source",
                         "Build parameters. Modify the JSON source and regenerate for dimensional changes.")
    assembly.DesignJSON = json.dumps(job["parameters"], ensure_ascii=False, sort_keys=True)
    assembly.setEditorMode("DesignJSON", 1)
    moving = None
    if job["hinge"]:
        center, direction = job["hinge"]
        moving = doc.addObject("App::Part", "HingedParts")
        assembly.addObject(moving)
        moving.addProperty("App::PropertyAngle", "OpeningAngle", "Motion", "Positive opens the cover")
        # Keep the imported world geometry at identity when closed, then rotate about the design pivot.
        def vector(coords):
            return "vector(" + ";".join(format(float(v), ".15g") for v in coords) + ")"
        expr = f"placement(vector(0;0;0);rotation({vector(direction)};OpeningAngle);{vector(center)})"
        moving.setExpression("Placement", expr)

    for i, row in enumerate(job["rows"], start=1):
        feature = doc.addObject("Part::Feature", f"Component{i:03d}")
        feature.Label = row["name"]
        feature.Shape = Part.read(str(Path(job["parts_root"]) / row["step"]))
        feature.addProperty("App::PropertyString", "MaterialName", "BOM")
        feature.MaterialName = row["material"]
        (moving if moving is not None and row["moving"] else assembly).addObject(feature)
    doc.recompute()
    doc.saveAs(job["target"])
    App.closeDocument(doc.Name)

    saved = App.openDocument(job["target"])
    restored = [o for o in saved.Objects if o.Name.startswith("Component")]
    for item in restored:
        if item.Shape.isNull() or not item.Shape.isValid() or not item.Shape.Solids:
            raise ValueError(f"Invalid solid in saved document: {item.Label}")
    if job["hinge"]:
        saved.HingedParts.OpeningAngle = 30
        saved.recompute()
        if abs(saved.HingedParts.Placement.Rotation.Angle - 0.52359878) > 1e-6:
            raise ValueError("The saved cover failed its native joint rotation check")
    App.closeDocument(saved.Name)
    Path(job["receipt"]).write_text(json.dumps({"components": len(restored)}), encoding="utf-8")


if __name__ == "__main__":
    create_document(json.loads(Path(os.environ["CAD_EXPORT_JOB"]).read_text(encoding="utf-8")))
