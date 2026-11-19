import tempfile
import unittest
from pathlib import Path

from consumer_cad_ai.geometry import verify_components
from consumer_cad_ai.recipe import load_recipe


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "desktop_stand.py"


class RecipeTests(unittest.TestCase):
    def test_custom_stand_parameters_and_geometry(self):
        parts, hinge, angles = load_recipe(EXAMPLE, {"width": 75})
        self.assertIsNone(hinge)
        report = verify_components(parts, hinge, angles)
        self.assertTrue(report["passed"], report["issues"])
        self.assertEqual(report["dimensions_mm"]["assembly_xyz"], [75, 56, 65])
        with self.assertRaisesRegex(ValueError, "Unknown stand parameters"):
            load_recipe(EXAMPLE, {"misspelled_width": 50})

    def test_hinged_recipe_reloads_edited_source_and_checks_motion(self):
        source = """
from build123d import Axis, Box, Pos
from consumer_cad_ai.geometry import Component
from consumer_cad_ai.recipe import Recipe

def build(parameters):
    fixed = Component("fixed", "Plastic", Pos(0, 4, 0) * Box(1, 2, 1))
    arm = Component("arm", "Metal", Pos(4, 0, 0) * Box(2, 1, 1), moving=True)
    return Recipe([fixed, arm], hinge=Axis.Z, angles_deg=(90, 90))
"""
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "my part.py"
            script.write_text(source, encoding="utf-8")
            parts, hinge, angles = load_recipe(script, {})
            self.assertEqual(angles, (0, 90))
            self.assertEqual(verify_components(parts, hinge, angles)["issues"][0]["angle_deg"], 90)
            script.write_text(source.replace("0, 4, 0", "0, 8, 0"), encoding="utf-8")
            self.assertTrue(verify_components(*load_recipe(script, {}))["passed"])

    def test_invalid_recipe_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.py"
            for code, error in [("x=1", "define build"),
                                ("def build(parameters): return []", "non-empty"),
                                ("def build(parameters): return [2]", "Component")]:
                with self.subTest(code=code), self.assertRaisesRegex(ValueError, error):
                    path.write_text(code, encoding="utf-8")
                    load_recipe(path, {})
