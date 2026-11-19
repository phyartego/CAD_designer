import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from consumer_cad_ai import pipeline


SIMPLE_RECIPE = """from build123d import Solid
from consumer_cad_ai.geometry import Component

def build(parameters):
    return [Component("pad", "Polymer", Solid.make_box(parameters["width"], 7, 3))]
"""


class PipelineTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.output = self.root / "case"
        self.recipe = self.root / "recipe with spaces.py"
        self.recipe.write_text(SIMPLE_RECIPE, encoding="utf-8")

    def test_local_recipe_source_manifest_and_artifacts(self):
        result = pipeline.run_recipe(self.recipe, {"width": 4}, self.output, freecad=False)
        self.assertTrue(result["passed"])
        self.assertEqual(result["output_dir"], str(self.output))
        self.assertEqual(json.loads((self.output / "manifest.json").read_text()), result)
        self.assertEqual(json.loads((self.output / "design.json").read_text()), {"width": 4})
        for path in result["artifacts"].values():
            self.assertFalse(Path(path).is_absolute())
            self.assertTrue((self.output / path).exists())
        self.assertNotIn("freecad", result["artifacts"])
        self.assertEqual((self.output / "recipe.py").read_bytes(), self.recipe.read_bytes())

    def test_build_declarative_spec_and_capture_resolved_defaults(self):
        sample = Path(__file__).resolve().parents[1] / "examples" / "sensor-clip.json"
        result = pipeline.run_spec(json.loads(sample.read_text()), self.output, freecad=False)
        self.assertTrue(result["passed"])
        self.assertEqual(result["verification"]["part_count"], 3)
        spec = json.loads((self.output / "design.json").read_text())
        self.assertEqual(spec["parts"][0]["features"][0]["op"], "add")
        self.assertEqual(spec["parts"][0]["rotation_deg"], [0, 0, 0])
        self.assertTrue((self.output / "assembly.step").is_file())

    def test_no_replace_if_empty_directory_appears_during_build(self):
        def racing_export(parts, data, stage, **kwargs):
            self.output.mkdir()
            return {}
        with patch.object(pipeline, "export_design", side_effect=racing_export):
            with self.assertRaises(FileExistsError):
                pipeline.run_recipe(self.recipe, {"width": 6}, self.output, freecad=False)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_keep_failed_report_without_exporting_invalid_assembly(self):
        result = pipeline.run_enclosure({"battery_thickness": 12}, self.output, freecad=False)
        self.assertFalse(result["passed"])
        self.assertTrue(any(i["code"] == "interference" for i in result["verification"]["issues"]))
        self.assertEqual({p.name for p in self.output.iterdir()}, {"design.json", "verification.json", "manifest.json"})
        self.assertEqual(json.loads((self.output / "design.json").read_text())["height"], 13)

    def test_malformed_parameters_preserve_reason(self):
        result = pipeline.run_enclosure({"typo": 1}, self.output, freecad=False)
        self.assertFalse(result["passed"])
        self.assertIn("typo", result["verification"]["issues"][0]["message"])

    def test_failed_export_publishes_nothing(self):
        def broken(parts, data, stage, **kwargs):
            (stage / "partial.step").touch()
            raise RuntimeError("simulated STEP failure")
        with patch.object(pipeline, "export_design", side_effect=broken):
            with self.assertRaisesRegex(RuntimeError, "STEP failure"):
                pipeline.run_recipe(self.recipe, {"width": 5}, self.output, freecad=False)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob(".cad-stage-*")))

    def test_preexisting_and_symlink_paths_are_rejected(self):
        self.output.mkdir()
        with self.assertRaises(FileExistsError):
            pipeline.run_enclosure({}, self.output)
        sentinel = self.output / "previous.txt"
        sentinel.write_text("previous")
        with self.assertRaises(FileExistsError):
            pipeline.run_enclosure({}, self.output)
        self.assertEqual(sentinel.read_text(), "previous")
        link = self.root / "link"
        try:
            link.symlink_to(self.output, target_is_directory=True)
        except OSError:
            self.skipTest("Current account cannot create symlinks")
        with self.assertRaises(FileExistsError):
            pipeline.run_enclosure({}, link)
        with self.assertRaises(ValueError):
            pipeline.run_enclosure({}, link / "new")

    def test_concurrent_publication_preserves_exactly_one_result(self):
        barrier = threading.Barrier(2)
        def publish_test_geometry(parts, data, stage, **kwargs):
            (stage / "chosen").write_text(str(data["width"]))
            barrier.wait(timeout=10)
            return {"chosen": "chosen"}
        def run(width):
            try:
                return pipeline.run_recipe(self.recipe, {"width": width}, self.output, freecad=False)
            except FileExistsError:
                return None
        with patch.object(pipeline, "export_design", side_effect=publish_test_geometry):
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(run, [4, 6]))
        self.assertEqual(sum(result is not None for result in outcomes), 1)
        chosen = (self.output / "chosen").read_text()
        self.assertEqual(chosen, str(json.loads((self.output / "design.json").read_text())["width"]))
        self.assertFalse(list(self.root.glob(".cad-stage-*")))

    def test_freecad_auto_and_explicit_modes(self):
        with patch.object(pipeline, "find_freecad", side_effect=FileNotFoundError("not installed")):
            with patch.dict("os.environ", FREECAD_CMD=""):
                self.assertIsNone(pipeline._freecad_command(None))
                with self.assertRaises(FileNotFoundError):
                    pipeline._freecad_command(True)
            with patch.dict("os.environ", FREECAD_CMD="/bad/config"):
                with self.assertRaises(FileNotFoundError):
                    pipeline._freecad_command(None)
                self.assertIsNone(pipeline._freecad_command(False))
