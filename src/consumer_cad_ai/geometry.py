"""Parametric B-rep assembly and sampled rigid-body checks, in millimetres.

Coordinates start at the lower left of the tray floor. X spans the two panels,
Y follows the hinge pin, and Z points out through the battery opening.
"""

from dataclasses import dataclass
from itertools import combinations
from math import ceil, isfinite

from build123d import Axis, Edge, Face, Plane, Shape, Solid, Wire

from .design import Design


@dataclass
class Component:
    name: str
    material: str
    shape: Shape
    moving: bool = False

    def __post_init__(self):
        self.shape.label = self.name


def _box(x, y, z, dx, dy, dz):
    return Solid.make_box(dx, dy, dz, Plane((x, y, z)))


def _cylinder(x, y, z, radius, length, axis=(0, 0, 1)):
    return Solid.make_cylinder(radius, length, Plane((x, y, z), z_dir=axis))


def screw(x, y, under_head_z, under_head_length):
    """Simplified M1.6 pan screw with nominal shank and cylindrical head."""
    shank = _cylinder(x, y, under_head_z - under_head_length, 0.8, under_head_length)
    head = _cylinder(x, y, under_head_z, 1.55, 0.85)
    return shank.fuse(head)


def pcb(x, y, z, length, width, thickness, hole_centers):
    board = _box(x, y, z, length, width, thickness)
    drills = [_cylinder(cx, cy, z - 1, 0.95, thickness + 2) for cx, cy in hole_centers]
    return board.cut(*drills) if drills else board


def battery(x, y, z, length, width, thickness):
    """Cell envelope. Add tab, cable and supplier-specific keep-outs as required."""
    return _box(x, y, z, length, width, thickness)


def compression_spring(x, y, z, installed_height, turns=3, radius=1.35, wire_radius=0.18):
    """Sweep round wire around a helix in its installed position."""
    if turns < 1 or radius <= wire_radius or wire_radius <= 0:
        raise ValueError("Spring requires positive wire, coil radius and turn count")
    rise = installed_height - 2 * wire_radius
    if rise / turns <= 2 * wire_radius:
        raise ValueError("Installed height must separate adjacent spring turns")
    path = Edge.make_helix(rise / turns, rise, radius, center=(x, y, z + wire_radius))
    section = Wire.make_circle(wire_radius, Plane(path.position_at(0), z_dir=path.tangent_at(0)))
    return Solid.sweep(section, path, is_frenet=True)


def _snap_arm(x, outer_y, inward_sign, base_z, lip_z, gap):
    """Cantilever with sloping insertion ramp and an undercut over the cell."""
    def pt(inset, z):
        return (x, outer_y + inward_sign * inset, z)
    outline = [pt(0, base_z), pt(1, base_z), pt(1, lip_z),
               pt(1 + gap + 0.45, lip_z), pt(1 + gap + 0.45, lip_z + 0.25),
               pt(0, lip_z + 1.0)]
    return Solid.extrude(Face(Wire.make_polygon(outline, close=True)), (3.5, 0, 0))


def battery_cradle(cx, cy, floor_z, cell_bottom, length, width, thickness, gap):
    """Locating pocket with two integral snap arms and spring aperture."""
    inner_x, inner_y = length + 2 * gap, width + 2 * gap
    x, y = cx - inner_x / 2 - 1, cy - inner_y / 2 - 1
    pedestal = _box(x, y, floor_z, inner_x + 2, inner_y + 2, cell_bottom - floor_z)
    pocket = _box(x + 1, y + 1, floor_z + 0.65, inner_x, inner_y, cell_bottom - floor_z)
    seat = pedestal.cut(pocket, _cylinder(cx, cy, floor_z - 1, 2.0, cell_bottom - floor_z + 2))
    seat = seat.cut(*[_cylinder(cx + side * length / 4, cy, floor_z - 1, 0.95, 2)
                      for side in (-1, 1)])
    lip_z = cell_bottom + thickness + 0.2
    arms = [_snap_arm(cx - 1.75, edge_y, direction, cell_bottom - 0.4, lip_z, gap)
            for edge_y, direction in [(y, 1), (y + inner_y + 2, -1)]]
    return seat.fuse(*arms)


def hinge_axis(d):
    return Axis((d.length + 2.1, 0, d.height + d.lid_gap + 0.6), (0, 1, 0))


def _hinge_leaf(d, start_y, end_y, moving):
    x, _, z = hinge_axis(d).position
    span = end_y - start_y
    barrel = _cylinder(x, start_y, z, 1.9, span, (0, 1, 0))
    if moving:
        web_z, web_h = d.height + d.lid_gap, min(d.lid_thickness, 1.2)
    else:
        web_z, web_h = d.height - 1.3, max(1.0, z - d.height + 1.2)
    web = _box(d.length - 0.3, start_y, web_z, x - d.length + 0.3, span, web_h)
    if not moving:
        # Relieve the fixed web beneath the moving panel inside the tray perimeter.
        web = web.cut(_box(d.length - 0.4, start_y - 1, d.height, 0.55, span + 2, web_h + 1))
    bore = _cylinder(x, start_y - 1, z, 0.9, span + 2, (0, 1, 0))
    return barrel.fuse(web).cut(bore)


def build_assembly(design: Design) -> list[Component]:
    d = design
    body = _box(0, 0, 0, d.length, d.width, d.height)
    cavity = _box(d.wall, d.wall, d.wall, d.length - 2 * d.wall,
                  d.width - 2 * d.wall, d.height)
    body = body.cut(cavity)
    lid_z = d.height + d.lid_gap
    # The fixed panel closes against the rim. Its two screws seat in integral posts.
    fixed = _box(0, 0, d.height, d.fixed_cover_length, d.width, d.lid_thickness)
    fixed_holes = [(4, 3), (d.fixed_cover_length - 4, d.width - 3)]
    pcb_x, pcb_y = (d.fixed_cover_length - d.pcb_length) / 2, (d.width - d.pcb_width) / 2
    pcb_z = d.wall + 2.0
    pcb_holes = [(pcb_x + 2.5, pcb_y + 2.5),
                 (pcb_x + d.pcb_length - 2.5, pcb_y + d.pcb_width - 2.5)]
    supports = [_cylinder(x, y, 0, 2.0, d.height) for x, y in fixed_holes]
    supports += [_cylinder(x, y, 0, 1.85, pcb_z) for x, y in pcb_holes]
    body = body.fuse(*supports, _hinge_leaf(d, 1, d.width * 0.22, False),
                     _hinge_leaf(d, d.width * 0.78, d.width - 1, False))
    # Mating threads are represented by clear bores; leave material below each bore.
    panel_depth = min(2.4, d.height * 0.6)
    board_depth = min(1.65, pcb_z * 0.6)
    body = body.cut(*[_cylinder(x, y, d.height - panel_depth, 0.83, panel_depth + 1)
                      for x, y in fixed_holes],
                    *[_cylinder(x, y, pcb_z - board_depth, 0.83, board_depth + 1)
                      for x, y in pcb_holes])
    fixed = fixed.cut(*[_cylinder(x, y, d.height - 1, 0.95, d.lid_thickness + 2)
                        for x, y in fixed_holes])
    lid_x = d.fixed_cover_length + d.clearance
    lid = _box(lid_x, 0, lid_z, d.length - lid_x, d.width, d.lid_thickness)
    lid = lid.fuse(_hinge_leaf(d, d.width * 0.28, d.width * 0.72, True))
    pin_x, _, pin_z = hinge_axis(d).position
    pin = _cylinder(pin_x, 0, pin_z, 0.75, d.width, (0, 1, 0))
    pin = pin.fuse(_cylinder(pin_x, 0, pin_z, 1.25, 0.8, (0, 1, 0)))
    groove_y = d.width - 0.9
    groove = _cylinder(pin_x, groove_y, pin_z, 0.8, 0.55, (0, 1, 0)).cut(
        _cylinder(pin_x, groove_y - 0.1, pin_z, 0.55, 0.75, (0, 1, 0)))
    pin = pin.cut(groove)
    clip = _cylinder(pin_x, groove_y + 0.05, pin_z, 1.25, 0.45, (0, 1, 0))
    clip = clip.cut(_cylinder(pin_x, groove_y, pin_z, 0.58, 0.6, (0, 1, 0)),
                    _box(pin_x, groove_y, pin_z - 0.32, 2, 0.6, 0.64))
    board = pcb(pcb_x, pcb_y, pcb_z, d.pcb_length, d.pcb_width, d.pcb_thickness, pcb_holes)
    cx, cy = (d.fixed_cover_length + d.length) / 2, d.width / 2
    cradle_holes = [(cx + side * d.battery_length / 4, cy) for side in (-1, 1)]
    cradle_depth = min(d.wall * 0.7, 1.4)
    body = body.cut(*[_cylinder(x, y, d.wall - cradle_depth, 0.83, cradle_depth + 1)
                      for x, y in cradle_holes])
    cell_z = d.wall + 2.8
    cell = battery(cx - d.battery_length / 2, cy - d.battery_width / 2, cell_z,
                   d.battery_length, d.battery_width, d.battery_thickness)
    bracket = battery_cradle(cx, cy, d.wall, cell_z, d.battery_length, d.battery_width,
                             d.battery_thickness, d.clearance)
    pad_thickness = 0.6
    lift_pad = _box(cx - d.battery_length / 2, cy - d.battery_width / 2, cell_z - pad_thickness,
                    d.battery_length, d.battery_width, pad_thickness)
    spring = compression_spring(cx, cy, d.wall, cell_z - d.wall - pad_thickness)
    parts = [Component("body", "Aluminium", body), Component("fixed_cover", "Aluminium", fixed),
             Component("battery_lid", "Aluminium", lid, moving=True),
             Component("hinge_pin", "Stainless steel", pin),
             Component("pin_clip", "Spring steel", clip), Component("pcb", "FR-4", board),
             Component("battery", "Pouch cell", cell), Component("snap_cradle", "Polymer", bracket),
             Component("lift_pad", "Polymer", lift_pad), Component("eject_spring", "Spring steel", spring)]
    for prefix, holes, top, length in [
        ("panel_screw", fixed_holes, d.height + d.lid_thickness, d.lid_thickness + panel_depth - 0.15),
        ("cradle_screw", cradle_holes, d.wall + 0.65, 0.65 + cradle_depth * 0.9),
        ("pcb_screw", pcb_holes, pcb_z + d.pcb_thickness, d.pcb_thickness + board_depth - 0.15),
    ]:
        parts.extend(Component(f"{prefix}_{i}", "Stainless steel", screw(x, y, top, length))
                     for i, (x, y) in enumerate(holes, start=1))
    return parts


def _overlap_volume(first, second):
    """Use the tested 0.10.x B-rep API. Face/edge-only contact has zero volume."""
    hit = first.intersect(second)
    if hit is None:
        return 0.0
    shapes = [hit] if isinstance(hit, Shape) else hit
    return sum(solid.volume for shape in shapes for solid in shape.solids())


def _box_overlap(a, b):
    return all(min(amax, bmax) - max(amin, bmin) > 1e-7
               for amin, amax, bmin, bmax in zip(a.min, a.max, b.min, b.max))


def _dimensions(bounds):
    return [round(value, 5) for value in bounds.size]


def verify_components(parts: list[Component], axis: Axis | None = None, angles_deg=(0.0,)) -> dict:
    """Measure arbitrary components and check all pairs. Moving parts form one rigid group."""
    if not parts or len({p.name for p in parts}) != len(parts):
        raise ValueError("Supply at least one component with unique names")
    angles = list(dict.fromkeys([0.0, *angles_deg]))
    if any(not isfinite(a) for a in angles) or (len(angles) > 1 and axis is None):
        raise ValueError("Nonzero sampled angles require a hinge axis and finite degrees")
    bounds = {p.name: p.shape.bounding_box() for p in parts}
    issues = []
    for p in parts:
        if not p.shape.is_valid or len(p.shape.solids()) != 1 or p.shape.volume <= 0:
            issues.append({"code": "invalid_solid", "part": p.name})

    def collision(a, b, pose, posed_shape=None, posed_bounds=None):
        a_shape = a.shape if posed_shape is None else posed_shape
        a_bounds = bounds[a.name] if posed_bounds is None else posed_bounds
        if not _box_overlap(a_bounds, bounds[b.name]):
            return
        volume = _overlap_volume(a_shape, b.shape)
        if volume > 1e-5:
            issues.append({"code": "interference", "parts": [a.name, b.name],
                           "angle_deg": pose, "overlap_mm3": round(volume, 6)})

    for a, b in combinations(parts, 2):
        collision(a, b, 0.0)
    for angle in angles[1:]:
        for part in parts:
            if part.moving:
                posed = part.shape.rotate(axis, angle)
                posed_bounds = posed.bounding_box()
                for static in parts:
                    if not static.moving:
                        collision(part, static, angle, posed, posed_bounds)
    overall = [round(max(highs) - min(lows), 5)
               for lows, highs in zip(zip(*(b.min for b in bounds.values())),
                                      zip(*(b.max for b in bounds.values())))]
    return {"passed": not issues, "issues": issues, "dimensions_mm": {
        "assembly_xyz": overall, "parts_xyz": {n: _dimensions(b) for n, b in bounds.items()}},
        "clearances_mm": {},
        "sweep": {"method": "sampled_rigid_poses", "angles_deg": angles,
                  "moving_parts": [p.name for p in parts if p.moving]},
        "part_count": len(parts), "overlap_volume_tolerance_mm3": 1e-5}


def verify(design: Design, parts: list[Component] | None = None) -> dict:
    """Apply the enclosure template's service clearances and rigid hinge sweep."""
    d = design
    parts = build_assembly(d) if parts is None else parts
    steps = ceil(d.open_angle_deg / d.sweep_step_deg)
    angles = [min(i * d.sweep_step_deg, d.open_angle_deg) for i in range(steps + 1)]
    report = verify_components(parts, hinge_axis(d), angles)
    bounds = {p.name: p.shape.bounding_box() for p in parts}
    # Actual flat panel undersides at the cell and PCB centre-lines. Hinge barrels
    # extend below this face, so the lid's bounding-box minimum is unsuitable.
    underside = d.height + d.lid_gap
    clearances = {
        "battery_to_lid": underside - bounds["battery"].max.Z,
        "snap_to_lid": underside - bounds["snap_cradle"].max.Z,
        "pcb_hardware_to_fixed_cover": d.height - max(bounds[n].max.Z for n in bounds
                                                       if n == "pcb" or n.startswith("pcb_screw_")),
        "battery_to_left_compartment_edge": bounds["battery"].min.X - d.fixed_cover_length,
        "battery_to_right_inner_wall": d.length - d.wall - bounds["battery"].max.X,
        "battery_to_side_walls": min(bounds["battery"].min.Y - d.wall,
                                     d.width - d.wall - bounds["battery"].max.Y),
        "cradle_to_end_wall": d.length - d.wall - bounds["snap_cradle"].max.X,
        "cradle_to_side_walls": min(bounds["snap_cradle"].min.Y - d.wall,
                                    d.width - d.wall - bounds["snap_cradle"].max.Y),
        "pcb_to_end_wall": bounds["pcb"].min.X - d.wall,
        "pcb_to_side_walls": min(bounds["pcb"].min.Y - d.wall, d.width - d.wall - bounds["pcb"].max.Y),
    }
    for name, gap in clearances.items():
        if gap < d.clearance - 1e-6:
            report["issues"].append({"code": "clearance", "measurement": name,
                           "actual_mm": round(gap, 5), "required_mm": d.clearance})
    report["clearances_mm"] = {k: round(v, 5) for k, v in clearances.items()}
    report["passed"] = not report["issues"]
    return report
