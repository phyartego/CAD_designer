import unittest
from unittest.mock import patch

from consumer_cad_ai.design import Design
from consumer_cad_ai.optimize import MAX_VERIFICATIONS, optimize_height


class OptimizeHeightTests(unittest.TestCase):
    def test_repairs_thick_cell_without_changing_hardware(self):
        original = Design(battery_thickness=12)
        result = optimize_height(original, 12, 22)
        self.assertEqual(result["status"], "minimum_verified")
        self.assertTrue(result["verification"]["passed"])
        self.assertFalse(result["trials"][0]["passed"])
        self.assertAlmostEqual(result["trials"][0]["worst_interference"]["overlap_mm3"], 600)
        self.assertLessEqual(len(result["trials"]), 3)
        self.assertEqual(result["design"]["height"], 18)
        self.assertEqual(result["design"], {**original.to_dict(), "height": 18})

    def test_reduces_excess_height_and_includes_non_grid_endpoint(self):
        result = optimize_height(Design(height=21), 10, 15, 0.25)
        self.assertTrue(result["passed"])
        self.assertEqual(result["design"]["height"], 10.75)
        self.assertLessEqual(len(result["trials"]), 3)
        endpoint = optimize_height(Design(height=21), 10, 10.8, 1)
        self.assertTrue(endpoint["passed"])
        self.assertEqual(endpoint["design"]["height"], 10.8)

    def test_infeasible_range_reports_actual_interference(self):
        result = optimize_height(Design(battery_thickness=12), 12, 13.4, 1)
        self.assertFalse(result["passed"])
        self.assertEqual(result["design"]["height"], 13.4)
        self.assertTrue(any(row["code"] == "interference" for row in result["unresolved_issues"]))
        self.assertLessEqual(len(result["trials"]), 2)

    def test_reports_invariant_lateral_failure(self):
        result = optimize_height(Design(pcb_width=39), 10, 40)
        self.assertFalse(result["passed"])
        self.assertEqual(result["status"], "infeasible_plan_clearance")
        self.assertEqual(len(result["trials"]), 1)

    def test_nonmonotonic_sweep_failure_respects_budget(self):
        def fail_sweep(design):
            gaps = dict.fromkeys(("battery_to_lid", "snap_to_lid", "pcb_hardware_to_fixed_cover"), design.height)
            return {"passed": False, "issues": [{"code": "interference", "angle_deg": 75, "overlap_mm3": 2}],
                    "clearances_mm": gaps}
        with patch("consumer_cad_ai.optimize.verify", side_effect=fail_sweep):
            result = optimize_height(Design(), 5, 70, 0.01)
        self.assertEqual(result["status"], "search_budget_exhausted")
        self.assertLessEqual(len(result["trials"]), MAX_VERIFICATIONS)
        self.assertEqual(result["design"]["height"], 70)
