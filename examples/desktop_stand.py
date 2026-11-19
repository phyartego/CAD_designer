"""Two-piece desktop phone stand. Dimensions are mm; tilt_deg is measured from vertical.

Change width, depth, height, tilt_deg or pad_thickness in the recipe parameters.
The backrest and raised front stop are integral to the aluminium stand; a
separate polymer pad rests against the inclined face.
"""

from math import cos, isfinite, radians, sin, tan

from build123d import Face, Plane, Solid, Wire

from consumer_cad_ai.geometry import Component


def _panel(x, span, yz):
    curve = Wire.make_polygon([(x, y, z) for y, z in yz], close=True)
    return Solid.extrude(Face(curve), (span, 0, 0))


def build(parameters):
    defaults = {"width": 62.0, "depth": 56.0, "height": 65.0, "tilt_deg": 15.0, "pad_thickness": 1.2}
    unknown = parameters.keys() - defaults.keys()
    if unknown:
        raise ValueError(f"Unknown stand parameters: {sorted(unknown)}")
    values = defaults | parameters
    if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not isfinite(v) for v in values.values()):
        raise ValueError("Stand parameters must be finite numbers")
    width, depth, height = values["width"], values["depth"], values["height"]
    tilt, thickness = values["tilt_deg"], values["pad_thickness"]
    if width <= 8 or height <= 20 or not 0 < thickness < 5 or not 0 <= tilt <= 45:
        raise ValueError("Require width > 8, height > 20, 0 < pad_thickness < 5 mm and 0 <= tilt_deg <= 45")
    a = radians(tilt)

    def y_front(z):
        return 18.0 + (z - 2.5) * tan(a)

    if depth < y_front(height) + 3:
        raise ValueError("Increase foot depth or reduce height or tilt to keep the support over the foot")
    bottom_y, top_y = y_front(2.5), y_front(height)
    base = Solid.make_box(width, depth, 3)
    lip = Solid.make_box(width, 3, 9, Plane((0, 2, 2.5)))
    support = _panel(0, width, [(bottom_y, 2.5), (bottom_y + 3, 2.5),
                                (top_y + 3, height), (top_y, height)])
    y0, z0, y1, z1 = y_front(10), 10, y_front(height - 4), height - 4
    dy, dz = -cos(a) * thickness, sin(a) * thickness
    pad = _panel(3, width - 6, [(y0, z0), (y1, z1), (y1 + dy, z1 + dz), (y0 + dy, z0 + dz)])
    return [Component("stand", "Aluminium", base.fuse(lip, support)), Component("pad", "Polymer", pad)]
