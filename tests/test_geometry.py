import json
import unittest
from dataclasses import replace
from pathlib import Path

from build123d import Plane, Solid

from consumer_cad_ai.design import Design
from consumer_cad_ai.geometry import Component, build_assembly, verify, verify_components


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "hinged-enclosure.json"


class GeometryTests(unittest.TestCase):
    def test_rebuild_example_and_sample_hinge(self):
        design = Design.from_dict(json.loads(EXAMPLE.read_text()))
        self.assertEqual(design.to_dict(), Design().to_dict())
        parts = build_assembly(design)
        report = verify(design, parts)
        self.assertEqual(report["issues"], [])
        self.assertTrue(report["passed"])
        self.assertEqual(len(parts), len({p.name for p in parts}))
        self.assertEqual(report["dimensions_mm"]["parts_xyz"]["battery"], [25, 20, 5])
        self.assertEqual(report["dimensions_mm"]["assembly_xyz"], [76, 40, 15.75])
        self.assertEqual(report["sweep"]["angles_deg"], [0, 15, 30, 45, 60, 75, 90, 105, 110])
        self.assertEqual(report["sweep"]["moving_parts"], ["battery_lid"])
        self.assertAlmostEqual(report["clearances_mm"]["battery_to_lid"], 3.85)

    def test_pouch_growth_detected_and_repaired(self):
        thick = Design(battery_thickness=12)
        report = verify(thick)
        self.assertFalse(report["passed"])
        hits = {row["angle_deg"]: row["overlap_mm3"] for row in report["issues"]
                if row["code"] == "interference" and set(row["parts"]) == {"battery_lid", "battery"}}
        self.assertAlmostEqual(hits[0], 600)
        self.assertGreater(hits[15], 10)
        self.assertTrue(verify(replace(thick, height=20))["passed"])

    def test_tiny_positive_separation_below_spec_is_reported(self):
        report = verify(Design(height=10.6))
        self.assertFalse(report["passed"])
        self.assertTrue(all(row["code"] == "clearance" for row in report["issues"]))
        self.assertTrue(any(row["measurement"] == "snap_to_lid" for row in report["issues"]))

    def test_obstacle_hits_only_intermediate_pose(self):
        design = Design()
        parts = build_assembly(design)
        gauge = Solid.make_sphere(0.5, Plane((60.1, 20, 38.1)))
        parts.append(Component("fixture", "Gauge", gauge))
        report = verify(design, parts)
        self.assertFalse(report["passed"])
        self.assertEqual([r["angle_deg"] for r in report["issues"]], [60])
        self.assertEqual(set(report["issues"][0]["parts"]), {"battery_lid", "fixture"})

    def test_general_parts_need_no_enclosure_template(self):
        body = Component("plate", "Alloy", Solid.make_box(4, 10, 2))
        pad = Component("pad", "Polymer", Solid.make_box(4, 10, 1, Plane((0, 0, 2))))
        result = verify_components([body, pad])
        self.assertTrue(result["passed"])
        self.assertEqual(result["dimensions_mm"]["assembly_xyz"], [4, 10, 3])
        self.assertEqual(result["sweep"]["angles_deg"], [0])
        with self.assertRaises(ValueError):
            verify_components([body, body])

    def test_reject_invalid_parameters(self):
        cases = [{"height": True}, {"length": "72"}, {"wall": float("nan")}, {"width": -40},
                 {"fixed_cover_length": 73}, {"sweep_step_deg": 0}, {"foo": 1}, []]
        for data in cases:
            with self.subTest(parameters=data), self.assertRaises(ValueError):
                Design.from_dict(data)
