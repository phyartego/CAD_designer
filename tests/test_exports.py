import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

import ezdxf
from build123d import Box, Pos, import_step

from consumer_cad_ai.exports import export_design
from consumer_cad_ai.freecad_bridge import find_freecad, write_fcstd
from consumer_cad_ai.geometry import Component


class ExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.path = Path(tmp.name)
        cls.parts = [
            Component("board", "FR-4", Box(12, 8, 1.6)),
            Component("cover", "Aluminium", Pos(Z=3.05) * Box(12, 8, 1.2), True),
        ]
        cls.files = export_design(cls.parts, {"gap": 1.65}, cls.path)

    def bom(self):
        with (self.path / self.files["bom"]).open(encoding="utf-8-sig") as source:
            return list(csv.DictReader(source))

    def test_step_labels_datum_and_bom(self):
        model = import_step(self.path / self.files["assembly"])
        self.assertEqual([part.label for part in model.children], [p.name for p in self.parts])
        self.assertEqual(len(model.solids()), 2)
        self.assertNotEqual(model.children[0].color, model.children[1].color)
        self.assertTrue(all(p.shape.parent is None for p in self.parts))
        rows = self.bom()
        self.assertEqual([r["name"] for r in rows], ["board", "cover"])
        for row, part in zip(rows, self.parts):
            restored = import_step(self.path / row["step"])
            self.assertAlmostEqual(restored.volume, part.shape.volume)
            for actual, expected in zip(restored.bounding_box().min, part.shape.bounding_box().min):
                self.assertAlmostEqual(actual, expected)
            self.assertAlmostEqual(float(row["volume_mm3"]), restored.volume)
            self.assertEqual(int(row["quantity"]), 1)

    def test_dxf_dimensions_and_print_outputs(self):
        dxf = ezdxf.readfile(self.path / self.files["drawing_dxf"])
        self.assertEqual(dxf.units, 4)  # millimetres
        self.assertFalse(dxf.audit().has_errors)
        space = dxf.modelspace()
        for view in ("TOP", "FRONT", "RIGHT"):
            self.assertGreaterEqual(len(space.query(f'*[layer=="{view}"]')), 4)
        dims = list(space.query("DIMENSION"))
        self.assertEqual(len(dims), 3)
        for dim, expected in zip(dims, [12, 8, 4.45]):
            self.assertAlmostEqual(dim.get_measurement(), expected, places=5)
        text = dxf.blocks[dims[-1].dxf.geometry].query("MTEXT")[0].dxf.text
        self.assertEqual(text, "4.45")
        self.assertTrue((self.path / self.files["drawing_pdf"]).read_bytes().startswith(b"%PDF-"))
        self.assertTrue((self.path / self.files["preview"]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_freecad_reopen_and_native_joint(self):
        try:
            executable = find_freecad()
        except FileNotFoundError:
            self.skipTest("FreeCAD console runtime unavailable")
        rows = self.bom()
        for row, part in zip(rows, self.parts):
            row["moving"] = part.moving
        target = write_fcstd(self.path, rows, {"gap": 1.65}, ((4, 0, 3), (0, 1, 0)), executable)
        with ZipFile(self.path / target) as native:
            document = native.read("Document.xml")
            self.assertIn(b"OpeningAngle", document)
            self.assertIn(b"DesignJSON", document)
            self.assertEqual(len([s for s in native.namelist() if s.endswith(".brp")]), len(self.parts))

    def test_missing_explicit_freecad_binary(self):
        with patch.dict("os.environ", FREECAD_CMD=str(self.path / "missing.exe")):
            with self.assertRaisesRegex(FileNotFoundError, "console executable not found"):
                find_freecad()
