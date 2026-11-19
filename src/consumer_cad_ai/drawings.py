"""Generate a dimensioned third-angle assembly drawing from OpenCascade projections."""

from pathlib import Path

import ezdxf
from build123d import Compound, ExportDXF, Pos, Vector
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
from ezdxf.enums import TextEntityAlignment
from matplotlib.figure import Figure


def _add_view(exporter, shape, direction, up, position, layer):
    center = shape.bounding_box().center()
    visible, _ = shape.project_to_viewport(
        center + Vector(direction), viewport_up=up, look_at=center
    )
    bounds = Compound(visible).bounding_box()
    offset = Pos(position[0] - bounds.center().X, position[1] - bounds.center().Y, 0)
    exporter.add_shape([edge.moved(offset) for edge in visible], layer=layer)
    return (position[0] - bounds.size.X / 2, position[1] - bounds.size.Y / 2,
            position[0] + bounds.size.X / 2, position[1] + bounds.size.Y / 2)


def write_drawings(assembly, parts, directory):
    """DXF geometry and dimension entities use mm; the PDF prints on landscape A4."""
    directory = Path(directory)
    size = assembly.bounding_box().size
    # All views share one scale. In DXF model space the parts always have full size.
    factor = max(size.X / 113, size.Y / 55, size.Z / 40, 0.2)
    exporter = ExportDXF()
    for layer in ("TOP", "FRONT", "RIGHT", "SERVICE"):
        exporter.add_layer(layer, line_weight=0.25)
    def xf(distance):
        return distance * factor

    def xy(x, y):
        return xf(x), xf(y)

    top = _add_view(exporter, assembly, (0, 0, 1), (0, 1, 0), xy(84, 147), "TOP")
    front = _add_view(exporter, assembly, (0, -1, 0), (0, 0, 1), xy(84, 65), "FRONT")
    _add_view(exporter, assembly, (1, 0, 0), (0, 0, 1), xy(214, 65), "RIGHT")
    # A second plan reveals the installed PCB and cell in the reference assembly.
    names = {part.name for part in parts}
    service_view = {"body", "fixed_cover", "battery_lid", "pcb", "battery"} <= names
    if service_view:
        covers = {"fixed_cover", "battery_lid"}
        inside = [p.shape for p in parts if p.name not in covers and not p.name.startswith("panel_screw_")]
        _add_view(exporter, Compound(inside), (0, 0, 1), (0, 1, 0), xy(214, 147), "SERVICE")

    dxf_path = directory / "assembly.dxf"
    exporter.write(str(dxf_path))
    drawing = ezdxf.readfile(dxf_path)
    space = drawing.modelspace()
    for layer, weight in (("ANNOTATIONS", 18), ("DIMENSIONS", 15), ("FRAME", 25)):
        drawing.layers.new(layer, dxfattribs={"lineweight": weight})

    def label(value, x, y, height=3, center=False):
        text = space.add_text(value, height=xf(height), dxfattribs={"layer": "ANNOTATIONS"})
        text.set_placement(xy(x, y), align=TextEntityAlignment.CENTER if center else TextEntityAlignment.LEFT)

    def dim(base, p1, p2, angle=0):
        style = {"dimtxt": xf(2.7), "dimasz": xf(1.8), "dimexo": xf(0.75),
                 "dimexe": xf(0.95), "dimgap": xf(0.6), "dimdec": 2, "dimrnd": 0.01,
                 "dimdsep": ord("."), "dimlfac": 1.0}
        space.add_linear_dim(base=base, p1=p1, p2=p2, angle=angle, dimstyle="Standard",
                             override=style, dxfattribs={"layer": "DIMENSIONS"}).render()

    x0, y0, x1, y1 = top
    dim((x0, y1 + xf(5)), (x0, y1), (x1, y1))
    dim((x0 - xf(6), y0), (x0, y0), (x0, y1), angle=90)
    x0, y0, x1, y1 = front
    dim((x1 + xf(6), y0), (x1, y0), (x1, y1), angle=90)
    space.add_lwpolyline([xy(6, 6), xy(291, 6), xy(291, 204), xy(6, 204)],
                         close=True, dxfattribs={"layer": "FRAME"})
    for y in (28, 188):
        space.add_line(xy(6, y), xy(291, y), dxfattribs={"layer": "FRAME"})
    label("Consumer electronics assembly", 12, 193, 5)
    label("GENERAL ARRANGEMENT", 214, 194, 3)
    label("TOP", 84, 109, center=True)
    label("FRONT", 84, 36, center=True)
    label("RIGHT", 214, 36, center=True)
    if service_view:
        label("SERVICE PLAN / COVERS REMOVED", 214, 109, center=True)
    label("Closed position  /  third-angle projection", 12, 17)
    label(f"{len(parts)} components  /  dimensions in mm", 12, 10, 2.6)
    label(f"Scale {1 / factor:.3g}:1 at A4", 211, 17)
    label("Sheet 1 of 1", 211, 10, 2.6)
    drawing.set_modelspace_vport(height=xf(210), center=xy(148.5, 105))
    drawing.saveas(dxf_path)

    # Render the same DXF entities for printing and for MCP image previews.
    fig = Figure(figsize=(297 / 25.4, 210 / 25.4), facecolor="white")
    ax = fig.add_axes([0, 0, 1, 1])
    config = Configuration(color_policy=ColorPolicy.BLACK, background_policy=BackgroundPolicy.WHITE)
    Frontend(RenderContext(drawing), MatplotlibBackend(ax, adjust_figure=False),
             config=config).draw_layout(space)
    ax.set_xlim(0, xf(297))
    ax.set_ylim(0, xf(210))
    ax.set_aspect("equal")
    ax.set_axis_off()
    fig.savefig(directory / "assembly.pdf", format="pdf",
                metadata={"Title": "Consumer electronics assembly | General arrangement"})
    fig.savefig(directory / "preview.png", format="png", dpi=120)
    fig.clear()
