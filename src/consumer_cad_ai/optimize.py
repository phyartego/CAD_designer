"""Search a height interval with the same solid/hinge checks used for exported designs."""

from dataclasses import replace
from math import ceil, isfinite

from .design import Design
from .geometry import verify


MAX_VERIFICATIONS = 24

# With fixed internals all three cover gaps increase 1 mm per mm of body height.
_COVER_GAPS = ("battery_to_lid", "snap_to_lid", "pcb_hardware_to_fixed_cover")
# A change of the Z dimension cannot correct these X/Y gaps.
_PLAN_GAPS = {
    "battery_to_left_compartment_edge", "battery_to_right_inner_wall", "battery_to_side_walls",
    "cradle_to_end_wall", "cradle_to_side_walls", "pcb_to_end_wall", "pcb_to_side_walls",
}


def optimize_height(design: Design, min_height: float, max_height: float, step: float = 0.5) -> dict:
    """Find the lowest feasible enclosure height on min_height + k*step, also testing max_height.

    Example: optimize_height(Design(battery_thickness=12), 12, 22, 0.5).
    Verify the input height (clamped to the interval), then use its measured cover gaps
    to skip provably undersized candidates. Rebuild and verify every returned design.
    Keep all other design parameters fixed. Up to 24 distinct CAD evaluations per call;
    a budget-limited search returns an explicit status and any known feasible height.
    """
    for value in (min_height, max_height, step):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            raise ValueError("Height bounds and step must be finite numbers")
    if not design.wall < min_height <= max_height or step <= 0:
        raise ValueError("Require wall < min_height <= max_height and a positive step")
    if min_height < max_height and max_height - step == max_height:
        raise ValueError("Step is below the numeric resolution of the height interval")

    reports = {}
    trials = []

    def evaluate(height):
        if height not in reports:
            report = verify(replace(design, height=height))
            reports[height] = report
            collisions = [item for item in report["issues"] if item["code"] == "interference"]
            worst = max(collisions, key=lambda item: item["overlap_mm3"], default=None)
            trials.append({"height": height, "passed": report["passed"],
                           "issue_count": len(report["issues"]), "worst_interference": worst,
                           "clearances_mm": report["clearances_mm"]})
        return reports[height]

    def result(height, status):
        report = reports[height]
        return {"passed": report["passed"], "status": status, "design": replace(design, height=height).to_dict(),
                "verification": report, "trials": trials, "unresolved_issues": report["issues"]}

    seed = min(max(design.height, min_height), max_height)
    initial = evaluate(seed)
    if any(issue.get("measurement") in _PLAN_GAPS for issue in initial["issues"]):
        return result(seed, "infeasible_plan_clearance")

    minimum_gap = min(initial["clearances_mm"][name] for name in _COVER_GAPS)
    # The report rounds to 0.00001 mm and the geometry checker accepts a 0.000001 mm
    # tolerance. Undershoot the theoretical lower bound before snapping to the grid.
    lower = seed + design.clearance - minimum_gap - 0.00001
    lower = min(max_height, max(min_height, lower))
    k = ceil((lower - min_height) / step)

    while len(reports) < MAX_VERIFICATIONS - 1:
        height = min(max_height, min_height + k * step)
        report = evaluate(height)
        if report["passed"]:
            return result(height, "minimum_verified")
        if height == max_height:
            return result(height, "infeasible_in_range")
        k += 1

    evaluate(max_height)
    feasible = [height for height, report in reports.items() if report["passed"]]
    if feasible:
        return result(min(feasible), "feasible_budget_limited")
    return result(max_height, "search_budget_exhausted")
