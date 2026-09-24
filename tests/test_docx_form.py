"""
The Word writer, checked by writing a document and reading it back.

Every assertion here goes through `_Doc`, which **unzips the generated .docx and
parses `word/document.xml` with lxml directly**. That is deliberate: the point of
these tests is to prove what is in the file a demonstrator will open, not to
replay the writer's own view of it. A test that asked `docx_form` what it had
written would pass just as happily if the writer were wrong in both directions.

`_Doc` also avoids the two traps the template sets (see
`docs/template-anatomy.md`): it unwraps cell-level content controls, and it
never calls lxml's `itertext()`.

The template is git-ignored — the user supplies their own — so the suite skips
rather than fails when it is absent. All data below is invented.
"""

import os
import random
import sys
import tempfile
import unittest
import zipfile

from lxml import etree

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coshh import docx_form  # noqa: E402
from coshh.docx_form import (  # noqa: E402
    ALWAYS_ON, CHECKED, COL_AMOUNT, COL_CONTROL, COL_HAZARDS, COL_NAME,
    COL_ROUTE, CONTROL_MEASURES, DEFAULT_TEMPLATE, EXPOSURE_ROUTES,
    RISK_ROWS, TABLE_APPROVAL, TABLE_HEADER, TABLE_RISK, TABLE_SCHEME,
    TABLE_SUBSTANCES, TABLE_WASTE, UNASSESSED_TEXT, UNCHECKED, WASTE_CELLS,
    CoshhForm,
)

W = docx_form.W
W14 = docx_form.W14

HAS_TEMPLATE = DEFAULT_TEMPLATE.is_file()
SKIP_WHY = "template not present at {} (the user supplies their own)".format(DEFAULT_TEMPLATE)


# --------------------------------------------------------------------------
# An independent reader: unzip, parse, walk.
# --------------------------------------------------------------------------

class _Doc(object):
    """Reads a .docx straight out of the zip, with no help from docx_form."""

    def __init__(self, path):
        with zipfile.ZipFile(str(path)) as zf:
            self.corrupt = zf.testzip()
            self.parts = zf.namelist()
            self.raw = zf.read("word/document.xml")
            # Prove the other parts a Word file needs still parse.
            for part in ("word/settings.xml", "[Content_Types].xml"):
                etree.fromstring(zf.read(part))
        self.root = etree.fromstring(self.raw)
        self.body = self.root.find(W + "body")
        self.tables = self.body.findall(W + "tbl")

    # -- structure --------------------------------------------------------

    def rows(self, table):
        return self.tables[table].findall(W + "tr")

    def cells(self, tr):
        out = []
        for child in tr:
            if child.tag == W + "tc":
                out.append(child)
            elif child.tag == W + "sdt":
                for tc in child.iter(W + "tc"):
                    out.append(tc)
                    break
        return out

    def cell(self, table, row, col):
        return self.cells(self.rows(table)[row])[col]

    def text(self, el):
        return "".join(t.text or "" for t in el.iter(W + "t"))

    def cell_text(self, table, row, col):
        return self.text(self.cell(table, row, col))

    # -- checkboxes -------------------------------------------------------

    def boxes(self, el):
        return [s for s in el.iter(W + "sdt")
                if s.find(W + "sdtPr/" + W14 + "checkbox") is not None]

    def checked(self, sdt):
        el = sdt.find(W + "sdtPr/" + W14 + "checkbox/" + W14 + "checked")
        return el is not None and el.get(W14 + "val") == "1"

    def glyph(self, sdt):
        return self.text(sdt.find(W + "sdtContent"))

    def label(self, sdt):
        p = sdt.getparent()
        if p is None or p.tag != W + "p":
            return ""
        before, after, seen = [], [], False
        for child in p:
            if child is sdt:
                seen = True
                continue
            if child.tag == W + "r":
                (after if seen else before).append(self.text(child))
        return ("".join(before) + "".join(after)).strip()

    def ticked_labels(self, table, row, col):
        return [self.label(b) for b in self.boxes(self.cell(table, row, col))
                if self.checked(b)]

    def all_boxes(self):
        return self.boxes(self.body)

    def sdt_ids(self):
        out = []
        for el in self.body.iter(W + "id"):
            parent = el.getparent()
            if parent is not None and parent.tag == W + "sdtPr":
                out.append(el.get(W + "val"))
        return out

    # -- the invariants every generated file must hold --------------------

    def assert_sound(self, case):
        case.assertIsNone(self.corrupt, "zip reports a corrupt member")
        mismatched = [self.label(b) or "<unlabelled>" for b in self.all_boxes()
                      if self.checked(b) != (self.glyph(b) == CHECKED)]
        case.assertEqual([], mismatched, "checkbox state disagrees with its glyph")
        for b in self.all_boxes():
            case.assertIn(self.glyph(b), (CHECKED, UNCHECKED))
        ids = self.sdt_ids()
        case.assertEqual(len(ids), len(set(ids)), "duplicate content-control ids")
        stray = [tc for tc in self.body.iter(W + "tc")
                 if tc.getparent().tag not in (W + "tr", W + "sdtContent")]
        case.assertEqual([], stray, "table cell outside w:tr/w:sdtContent")


# --------------------------------------------------------------------------

ASSESSMENT = {
    "title": "Bromination of an activated arene",
    "name": "Test Student",
    "date": "2099-01-31",
    "college": "Test College",
    "year": "2",
    "scheme_note": "ArH + Br2 -> ArBr + HBr",
    "substances": [
        {
            "name": "Bromine",
            "cas": "7726-95-6",
            "amount": "2.0 mL",
            "hazards": [
                {"code": "H330", "text": "Fatal if inhaled"},
                {"code": "H314", "text": "Causes severe skin burns and eye damage"},
            ],
            "exposure": ["Eyes", "Skin", "Inhalation"],
            "controls": ["Gloves", "Fumehood", "Add dropwise to solution"],
        },
        {
            "name": "Dichloromethane",
            "cas": "75-09-2",
            "amount": "25 mL",
            "hazards": [{"code": "H351", "text": "Suspected of causing cancer"}],
            "exposure": ["Inhalation"],
            "controls": ["Fumehood", "Not to be used if pregnant"],
        },
        {
            "name": "Invented Reagent Q",
            "cas": None,
            "amount": "0.5 g",
            "hazards": [],
            "exposure": [],
            "controls": ["Gloves"],
            "unknown": True,
            "note": "Supplier bottle carries no GHS label.",
        },
    ],
    "implications": {
        "Gas Release": {"yes": True, "prevention": "HBr evolved; keep in the fumehood."},
        "Fire or Explosion": {"yes": False, "prevention": ""},
    },
    "waste": ["Halogenated", "Aqueous"],
    "waste_note": "Bromine residues quenched with thiosulfate before disposal.",
}


@unittest.skipUnless(HAS_TEMPLATE, SKIP_WHY)
class RenderTest(unittest.TestCase):
    """One rendered document, read back from the zip and interrogated."""

    @classmethod
    def setUpClass(cls):
        random.seed(20990131)   # clone ids are random; keep failures reproducible
        cls._tmp = tempfile.TemporaryDirectory()
        cls.path = os.path.join(cls._tmp.name, "rendered.docx")
        cls.report = docx_form.render(ASSESSMENT, cls.path)
        cls.doc = _Doc(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    # -- the file itself ---------------------------------------------------

    def test_file_is_structurally_sound(self):
        self.doc.assert_sound(self)
        self.assertIn("word/document.xml", self.doc.parts)
        self.assertIn("word/header1.xml", self.doc.parts)

    def test_header_fields_land_in_their_own_cells(self):
        self.assertEqual("Bromination of an activated arene",
                         self.doc.cell_text(TABLE_HEADER, 0, 1))
        self.assertEqual("Test Student", self.doc.cell_text(TABLE_HEADER, 1, 1))
        self.assertEqual("2099-01-31", self.doc.cell_text(TABLE_HEADER, 1, 3))
        self.assertEqual("Test College", self.doc.cell_text(TABLE_HEADER, 2, 1))
        # The labels in column 0 are untouched.
        self.assertIn("Title", self.doc.cell_text(TABLE_HEADER, 0, 0))
        self.assertIn("College", self.doc.cell_text(TABLE_HEADER, 2, 0))

    def test_year_is_underlined_not_replaced(self):
        cell = self.doc.cell(TABLE_HEADER, 2, 3)
        self.assertEqual("1  /  2  /  3", self.doc.text(cell))
        underlined = []
        for r in cell.iter(W + "r"):
            rPr = r.find(W + "rPr")
            if rPr is not None and rPr.find(W + "u") is not None:
                underlined.append(self.doc.text(r))
        self.assertEqual(["2"], underlined)

    def test_reaction_scheme_written_without_placeholder_styling(self):
        cell = self.doc.cell(TABLE_SCHEME, 1, 0)
        self.assertEqual("ArH + Br2 -> ArBr + HBr", self.doc.text(cell))
        self.assertNotIn("Write out your reaction scheme", self.doc.raw.decode("utf-8"))
        for pPr in cell.iter(W + "pPr"):
            rPr = pPr.find(W + "rPr")
            if rPr is not None:
                self.assertIsNone(rPr.find(W + "rStyle"))
                self.assertIsNone(rPr.find(W + "i"))

    # -- the substance table ----------------------------------------------

    def test_worked_example_is_gone(self):
        # The example's name is split across runs ("3 M HNO" + a subscript "3"),
        # so substring-matching the raw XML would pass whatever happened. Match
        # the fragment that cannot split, and the joined cell text.
        self.assertNotIn("HNO", self.doc.raw.decode("utf-8"))
        self.assertEqual("Bromine", self.doc.cell_text(TABLE_SUBSTANCES, 1, COL_NAME))
        self.assertNotIn("e.g.", self.doc.cell_text(TABLE_SUBSTANCES, 1, COL_NAME))

    def test_one_row_per_substance_plus_the_templates_blank_rows(self):
        # 3 substances, but the template ships 4 blank rows and we never shrink.
        self.assertEqual(1 + 4, len(self.doc.rows(TABLE_SUBSTANCES)))

    def test_substance_text_lands_in_the_right_columns(self):
        self.assertEqual("Bromine", self.doc.cell_text(TABLE_SUBSTANCES, 1, COL_NAME))
        self.assertEqual("2.0 mL", self.doc.cell_text(TABLE_SUBSTANCES, 1, COL_AMOUNT))
        self.assertEqual("Dichloromethane", self.doc.cell_text(TABLE_SUBSTANCES, 2, COL_NAME))
        self.assertEqual("25 mL", self.doc.cell_text(TABLE_SUBSTANCES, 2, COL_AMOUNT))

    def test_hazards_render_one_code_per_paragraph(self):
        cell = self.doc.cell(TABLE_SUBSTANCES, 1, COL_HAZARDS)
        lines = [self.doc.text(p) for p in cell.findall(W + "p")]
        self.assertEqual(
            ["H330 - Fatal if inhaled",
             "H314 - Causes severe skin burns and eye damage"],
            lines,
        )

    def test_exposure_routes_ticked_exactly(self):
        self.assertEqual(["Eyes", "Skin", "Inhalation"],
                         self.doc.ticked_labels(TABLE_SUBSTANCES, 1, COL_ROUTE))
        self.assertEqual(["Inhalation"],
                         self.doc.ticked_labels(TABLE_SUBSTANCES, 2, COL_ROUTE))
        # A substance with no route claimed has none ticked.
        self.assertEqual([], self.doc.ticked_labels(TABLE_SUBSTANCES, 3, COL_ROUTE))

    def test_controls_are_additive_over_the_standing_defaults(self):
        ticked = self.doc.ticked_labels(TABLE_SUBSTANCES, 1, COL_CONTROL)
        for standing in ALWAYS_ON:
            self.assertIn(standing, ticked)
        self.assertIn("Gloves", ticked)
        self.assertIn("Fumehood", ticked)
        self.assertIn("Add dropwise to solution", ticked)
        # and nothing else crept in
        self.assertEqual(set(ALWAYS_ON) | {"Gloves", "Fumehood", "Add dropwise to solution"},
                         set(ticked))

    def test_controls_do_not_leak_between_rows(self):
        row2 = set(self.doc.ticked_labels(TABLE_SUBSTANCES, 2, COL_CONTROL))
        self.assertNotIn("Gloves", row2)
        self.assertNotIn("Add dropwise to solution", row2)
        self.assertIn("Not to be used if pregnant", row2)

    def test_every_control_measure_option_is_present_on_every_row(self):
        for row in range(1, len(self.doc.rows(TABLE_SUBSTANCES))):
            labels = [self.doc.label(b)
                      for b in self.doc.boxes(self.doc.cell(TABLE_SUBSTANCES, row, COL_CONTROL))]
            self.assertEqual(list(CONTROL_MEASURES), labels)
            routes = [self.doc.label(b)
                      for b in self.doc.boxes(self.doc.cell(TABLE_SUBSTANCES, row, COL_ROUTE))]
            self.assertEqual(list(EXPOSURE_ROUTES), routes)

    def test_unassessed_substance_shouts_in_the_hazards_cell(self):
        cell_text = self.doc.cell_text(TABLE_SUBSTANCES, 3, COL_HAZARDS)
        self.assertIn(UNASSESSED_TEXT, cell_text)
        self.assertIn("safety data sheet", cell_text)
        self.assertIn("Supplier bottle carries no GHS label.", cell_text)

    def test_blank_rows_stay_blank_but_keep_their_standing_ticks(self):
        self.assertEqual("", self.doc.cell_text(TABLE_SUBSTANCES, 4, COL_NAME).strip())
        self.assertEqual(list(ALWAYS_ON),
                         self.doc.ticked_labels(TABLE_SUBSTANCES, 4, COL_CONTROL))

    # -- risk, waste, signature -------------------------------------------

    def test_risk_row_ticks_only_what_was_claimed(self):
        gas = RISK_ROWS["Gas Release"]
        self.assertTrue(self.doc.checked(self.doc.boxes(self.doc.cell(TABLE_RISK, gas, 1))[0]))
        self.assertEqual("HBr evolved; keep in the fumehood.",
                         self.doc.cell_text(TABLE_RISK, gas, 2).strip())
        for label, row in RISK_ROWS.items():
            if label != "Gas Release":
                box = self.doc.boxes(self.doc.cell(TABLE_RISK, row, 1))[0]
                self.assertFalse(self.doc.checked(box), "{} should be unticked".format(label))

    def test_waste_streams_ticked_by_position(self):
        ticked = [label for label, (r, c) in WASTE_CELLS.items()
                  if self.doc.checked(self.doc.boxes(self.doc.cell(TABLE_WASTE, r, c))[0])]
        self.assertEqual({"Halogenated", "Aqueous"}, set(ticked))
        self.assertIn("thiosulfate", self.doc.cell_text(TABLE_WASTE, 0, 1))

    def test_approved_by_is_never_filled(self):
        self.assertEqual("", self.doc.cell_text(TABLE_APPROVAL, 0, 1).strip())
        self.assertEqual("", self.doc.cell_text(TABLE_APPROVAL, 0, 3).strip())
        self.assertIn("Approved By", self.doc.cell_text(TABLE_APPROVAL, 0, 0))

    # -- the report --------------------------------------------------------

    def test_report_names_what_a_human_must_still_do(self):
        self.assertEqual(["Bromine", "Dichloromethane", "Invented Reagent Q"],
                         self.report.substances)
        self.assertEqual(["Invented Reagent Q"], self.report.unassessed)
        joined = " | ".join(self.report.needs_review)
        self.assertIn("Invented Reagent Q", joined)
        self.assertIn("Approved By", joined)
        self.assertIn("Scale and containment", joined)


@unittest.skipUnless(HAS_TEMPLATE, SKIP_WHY)
class RowCloningTest(unittest.TestCase):
    """More substances than the template has rows."""

    def _render(self, n, **kw):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "many.docx")
        assessment = {
            "title": "Cloning check",
            "substances": [{"name": "Substance {}".format(i), "amount": "{} mL".format(i),
                            "hazards": [{"code": "H319", "text": "Causes serious eye irritation"}],
                            "exposure": ["Eyes"], "controls": ["Gloves"]}
                           for i in range(n)],
        }
        docx_form.render(assessment, path, **kw)
        return _Doc(path)

    def test_nine_substances_get_nine_rows_with_unique_control_ids(self):
        random.seed(7)
        doc = self._render(9)
        doc.assert_sound(self)
        self.assertEqual(1 + 9, len(doc.rows(TABLE_SUBSTANCES)))
        for i in range(9):
            self.assertEqual("Substance {}".format(i),
                             doc.cell_text(TABLE_SUBSTANCES, 1 + i, COL_NAME))
            self.assertEqual(["Eyes"], doc.ticked_labels(TABLE_SUBSTANCES, 1 + i, COL_ROUTE))
            self.assertIn("Gloves", doc.ticked_labels(TABLE_SUBSTANCES, 1 + i, COL_CONTROL))

    def test_cloned_rows_carry_a_full_set_of_checkboxes(self):
        random.seed(11)
        doc = self._render(9)
        # 4 routes + 11 controls per data row, plus the template's fixed boxes.
        per_row = len(EXPOSURE_ROUTES) + len(CONTROL_MEASURES)
        for i in range(9):
            row = doc.rows(TABLE_SUBSTANCES)[1 + i]
            self.assertEqual(per_row, len(doc.boxes(row)))

    def test_keeping_the_example_row_keeps_its_placeholder(self):
        random.seed(13)
        doc = self._render(2, keep_example=True)
        doc.assert_sound(self)
        self.assertEqual("e.g. 3 M HNO3", doc.cell_text(TABLE_SUBSTANCES, 1, COL_NAME))
        # data rows start after the example
        self.assertEqual("Substance 0", doc.cell_text(TABLE_SUBSTANCES, 2, COL_NAME))


@unittest.skipUnless(HAS_TEMPLATE, SKIP_WHY)
class ReadBackTest(unittest.TestCase):
    """`open_document` re-opens a generated file and reports what landed."""

    def test_generated_file_reports_its_own_contents(self):
        random.seed(3)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "readback.docx")
        docx_form.render(ASSESSMENT, path)

        form = docx_form.open_document(path)
        self.assertEqual("Bromination of an activated arene", form.header_values()["title"])
        self.assertEqual("1  /  2  /  3", form.header_values()["year"])

        row = form.substance_row_values(0)
        self.assertEqual("Bromine", row["name"])
        self.assertEqual("2.0 mL", row["amount"])
        self.assertIn("H330 - Fatal if inhaled", row["hazards"])
        self.assertEqual(["Eyes", "Skin", "Inhalation"], row["routes"])
        self.assertIn("Fumehood", row["controls"])

        self.assertTrue(form.risk_values()["Gas Release"]["yes"])
        self.assertFalse(form.risk_values()["Thermal Runaway"]["yes"])
        self.assertEqual({"Halogenated", "Aqueous"}, set(form.waste_values()))

    def test_a_generated_file_still_passes_validation(self):
        random.seed(5)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "roundtrip.docx")
        docx_form.render(ASSESSMENT, path)
        docx_form.open_document(path).validate()   # raises if anything is off
        self.assertIn("word/document.xml", docx_form.document_parts(path))


@unittest.skipUnless(HAS_TEMPLATE, SKIP_WHY)
class RefusalTest(unittest.TestCase):
    """The writer complains rather than quietly doing nothing."""

    def setUp(self):
        self.form = CoshhForm()
        self.form.prepare_substance_rows(1)

    def test_unknown_control_measure_raises(self):
        with self.assertRaises(ValueError) as cm:
            self.form.fill_substance(0, name="Test substance", controls=["Respirator"])
        self.assertIn("Respirator", str(cm.exception))

    def test_unknown_exposure_route_raises(self):
        with self.assertRaises(ValueError):
            self.form.fill_substance(0, name="Test substance", routes=["Dermal"])

    def test_unknown_risk_row_raises(self):
        with self.assertRaises(ValueError):
            self.form.set_risk("Earthquake", True)

    def test_unknown_waste_stream_raises(self):
        with self.assertRaises(ValueError):
            self.form.set_waste(["Radioactive"])

    def test_row_beyond_the_table_raises(self):
        with self.assertRaises(IndexError):
            self.form.fill_substance(99, name="Test substance")

    def test_bad_year_raises(self):
        with self.assertRaises(ValueError):
            self.form.set_year(4)

    def test_saving_a_signed_form_is_refused(self):
        docx_form._write_cell(self.form._cell(TABLE_APPROVAL, 0, 1), "Dr Someone")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with self.assertRaises(ValueError) as cm:
            self.form.save(os.path.join(tmp.name, "signed.docx"))
        self.assertIn("Approved By", str(cm.exception))

    def test_a_desynced_checkbox_is_refused(self):
        """Write only the glyph, as a naive implementation would, and get caught."""
        cell = self.form._cell(TABLE_SUBSTANCES, 1, COL_ROUTE)
        box = docx_form._checkboxes(cell)[0]
        box.find(W + "sdtContent/" + W + "r/" + W + "t").text = CHECKED
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with self.assertRaises(ValueError) as cm:
            self.form.save(os.path.join(tmp.name, "desynced.docx"))
        self.assertIn("glyph", str(cm.exception))

    def test_missing_template_is_a_clear_error(self):
        with self.assertRaises(FileNotFoundError) as cm:
            CoshhForm("/nonexistent/path/to/template.docx")
        self.assertIn("template", str(cm.exception).lower())


@unittest.skipUnless(HAS_TEMPLATE, SKIP_WHY)
class TemplateShapeTest(unittest.TestCase):
    """The assumptions the writer is built on, asserted against the template."""

    @classmethod
    def setUpClass(cls):
        cls.doc = _Doc(DEFAULT_TEMPLATE)

    def test_six_tables(self):
        self.assertEqual(6, len(self.doc.tables))

    def test_every_checkbox_agrees_with_its_glyph(self):
        self.doc.assert_sound(self)

    def test_control_measure_labels_match_the_constant(self):
        labels = [self.doc.label(b)
                  for b in self.doc.boxes(self.doc.cell(TABLE_SUBSTANCES, 2, COL_CONTROL))]
        self.assertEqual(list(CONTROL_MEASURES), labels)

    def test_blank_rows_ship_with_the_standing_ticks(self):
        self.assertEqual(list(ALWAYS_ON),
                         self.doc.ticked_labels(TABLE_SUBSTANCES, 2, COL_CONTROL))

    def test_risk_rows_are_where_the_constant_says(self):
        for label, row in RISK_ROWS.items():
            self.assertIn(label.rstrip(":"),
                          self.doc.cell_text(TABLE_RISK, row, 0))

    def test_waste_labels_sit_beside_their_boxes(self):
        for label, (row, col) in WASTE_CELLS.items():
            self.assertEqual(label, self.doc.cell_text(TABLE_WASTE, row, col + 1).strip())


if __name__ == "__main__":
    unittest.main()
