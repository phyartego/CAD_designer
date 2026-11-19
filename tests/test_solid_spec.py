import json
import unittest
from pathlib import Path

from consumer_cad_ai.geometry import verify_components
from consumer_cad_ai.solid_spec import build_spec, spec_schema


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sensor-clip.json"


def part(name="bracket", **kwargs):
    return {"name": name, "material": "ABS", "features": [{"kind": "box", "size": [2, 2, 3]}]} | kwargs


class SolidSpecTests(unittest.TestCase):
    def test_slide_in_board_and_sensor(self):
        spec = json.loads(EXAMPLE.read_text())
        parts, hinge, angles = build_spec(spec)
        report = verify_components(parts, hinge, angles)
        self.assertTrue(report["passed"], report["issues"])
        self.assertEqual(report["dimensions_mm"]["assembly_xyz"], [26, 20, 8])
        # Changing the board thickness produces an actual collision with its retention rails.
        spec["parts"][1]["features"][0]["size"][2] = 3
        report = verify_components(*build_spec(spec))
        self.assertFalse(report["passed"])
        self.assertIn(["clip", "sensor_board"], [r["parts"] for r in report["issues"]])

    def test_feature_then_part_transforms_and_pose(self):
        payload = {"parts": [
            part("arm", moving=True, features=[{"kind": "cylinder", "radius": 1, "height": 4,
                 "rotation_deg": [0, 90, 0], "origin": [1, 0, 0]}], rotation_deg=[0, 0, 90]),
            part("stop", origin=[-4, -1, -1])],
            "hinge": {"origin": [0, 0, 0], "direction": [0, 0, 2], "angles_deg": [90]}}
        parts, axis, angles = build_spec(payload)
        self.assertEqual(angles, (0, 90))
        self.assertAlmostEqual(parts[0].shape.bounding_box().min.Y, 1, places=5)
        result = verify_components(parts, axis, angles)
        self.assertEqual([i["angle_deg"] for i in result["issues"]], [90])

    def test_disconnected_intermediate_fused_by_later_bridge(self):
        p = part(features=[{"kind": "box", "size": [2, 2, 2], "origin": [x, 0, 0]}
                           for x in (0, 4, 2)])
        parts, _, _ = build_spec({"parts": [p]})
        self.assertAlmostEqual(parts[0].shape.volume, 24)

    def test_schema_limits_and_unsupported_operations(self):
        schema = spec_schema()
        self.assertFalse(schema["additionalProperties"])
        self.assertIn("Cylinder", schema["$defs"])
        feature = {"kind": "box", "size": [1, 1, 1]}
        cases = [
            {"parts": [part(features=[feature | {"op": "cut"}])]},
            {"parts": [part(features=[feature | {"size": [True, 1, 1]}])]},
            {"parts": [part(features=[feature | {"size": [0, 1, 1]}])]},
            {"parts": [part(features=[feature | {"kind": "python"}])]},
            {"parts": [part(features=[feature, feature | {"op": "cut"}])]},
            {"parts": [part(features=[feature, feature | {"origin": [4, 0, 0]}])]},
            {"parts": [part(features=[feature] * 25)]},
            {"parts": [part("a"), part("a")]},
            {"parts": [part(f"a{i}", features=[feature] * 20) for i in range(5)]},
            {"parts": [part("a", moving=True)], "hinge": {"origin": [0, 0, 0],
             "direction": [0, 0, 0], "angles_deg": [10]}},
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                build_spec(case)
