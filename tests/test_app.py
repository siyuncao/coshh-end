"""
Tests for the web layer.

The app owns one piece of reasoning and one piece only: folding a chemist's
corrections back into the assessment the reader produced. Everything else it
delegates. So most of what is worth testing here is `corrected()` — and in
particular the places where "the chemist unticked a box" has to survive all the
way into the document, because a control measure that silently stays on is a
control measure somebody believes is on the form.

No network: the assessment fixture is produced by running `manual.assess` with
the same injected fakes the reader's own tests use.
"""

import json
import unittest

from fastapi.testclient import TestClient

import app as webapp
from coshh import docx_form, rules
from tests.test_manual import extractor, looker, pubchem, substance


# --------------------------------------------------------------------------
# A real assessment, produced by running the reader offline
# --------------------------------------------------------------------------

def assessment():
    """Two classified substances, one PubChem cannot place, one bit of kit."""
    from coshh import manual

    return manual.assess(
        "To a stirred solution of toluene (2.12 g, 23 mmol) in DCM was added "
        "concentrated nitric acid (1.5 mL) dropwise at 0 C using an ice bath. "
        "Ganymedene (3 g) was then added.",
        title="Nitration of toluene", name="A Chemist", date="2026-09-24",
        college="Example College", year="2",
        extractor=extractor(
            scheme="Nitration of toluene",
            substances=[substance("toluene", "2.12 g, 23 mmol"),
                        substance("nitric acid", "1.5 mL"),
                        substance("ganymedene", "3 g")],
            equipment=[{"name": "ice bath", "note": "", "source_line": "at 0 C"}]),
        lookup=looker({
            "toluene": pubchem("toluene", "H225", "H304", "H315", "H336"),
            "nitric acid": pubchem("nitric acid", "H272", "H314", "H330")}))


def form_pairs(data, **overrides):
    """The POST body a chemist who changed nothing would send."""
    rows = data["substances"]
    order = list(data["implications"])
    pairs = [("baseline", json.dumps(data)), ("order", json.dumps(order))]
    for key in ("title", "name", "date", "college", "year"):
        pairs.append((key, data.get(key, "")))
    pairs.append(("scheme_note", data.get("scheme_note") or ""))
    for i, row in enumerate(rows):
        pairs.append(("include_%d" % i, "y"))
        pairs.append(("name_%d" % i, row.get("name", "")))
        pairs.append(("amount_%d" % i, row.get("amount", "")))
        pairs.append(("hazards_%d" % i, webapp.hazard_lines(row)))
        for route in row.get("exposure") or ():
            pairs.append(("route_%d" % i, route))
        for control in row.get("controls") or ():
            pairs.append(("control_%d" % i, control))
    for idx, key in enumerate(order):
        value = data["implications"][key]
        if value.get("yes"):
            pairs.append(("risk_%d" % idx, "y"))
        pairs.append(("prevention_%d" % idx, value.get("prevention") or ""))
    for stream in data.get("waste") or ():
        pairs.append(("waste", stream))
    pairs.append(("waste_note", data.get("waste_note") or ""))
    return [(k, v) for k, v in pairs if k not in overrides] + list(overrides.items())


def as_data(pairs):
    """Pairs as httpx wants them: one key, a list of its values."""
    out = {}
    for key, value in pairs:
        out.setdefault(key, []).append(value)
    return out


class FakeForm(dict):
    """The little of Starlette's FormData that `corrected()` uses."""

    def __init__(self, pairs):
        super().__init__()
        self._pairs = list(pairs)
        for key, value in self._pairs:
            self.setdefault(key, value)

    def getlist(self, key):
        return [v for k, v in self._pairs if k == key]


def fold(pairs):
    data = json.loads(dict(pairs)["baseline"])
    return webapp.corrected(data, FakeForm(pairs))


def row_named(data, name):
    for row in data["substances"]:
        if row["name"] == name:
            return row
    raise AssertionError("%s not in %s" % (name, [r["name"] for r in data["substances"]]))


# --------------------------------------------------------------------------
# The promise that matters most: an unticked box is unticked
# --------------------------------------------------------------------------

class UntickingTest(unittest.TestCase):
    """`fill_substance` is additive and the template ships three ticks already on."""

    def setUp(self):
        self.data = assessment()

    def test_unticking_a_standing_control_sends_it_as_controls_off(self):
        pairs = [(k, v) for k, v in form_pairs(self.data)
                 if not (k == "control_0" and v == "Lab coat")]
        row = fold(pairs)["substances"][0]
        self.assertNotIn("Lab coat", row["controls"])
        self.assertIn("Lab coat", row["controls_off"],
                      "an unticked standing control must be turned off explicitly, "
                      "or the template's own tick survives into the document")

    def test_controls_off_is_every_option_the_chemist_did_not_pick(self):
        row = fold(form_pairs(self.data))["substances"][0]
        both = set(row["controls"]) | set(row["controls_off"])
        self.assertEqual(both, set(docx_form.CONTROL_MEASURES))
        self.assertFalse(set(row["controls"]) & set(row["controls_off"]))

    def test_unticking_every_route_is_a_claim_the_form_makes(self):
        pairs = [(k, v) for k, v in form_pairs(self.data) if k != "route_0"]
        self.assertEqual(fold(pairs)["substances"][0]["exposure"], [])

    def test_an_untick_survives_into_the_document(self):
        pairs = [(k, v) for k, v in form_pairs(self.data)
                 if not (k == "control_1" and v == "Fumehood")]
        with TestClient(webapp.app) as client:
            response = client.post("/document", data=as_data(pairs))
        self.assertEqual(response.status_code, 200)
        import tempfile, os
        handle, path = tempfile.mkstemp(suffix=".docx")
        os.close(handle)
        try:
            with open(path, "wb") as fh:
                fh.write(response.content)
            controls = docx_form.open_document(path).substance_row_values(1)["controls"]
        finally:
            os.unlink(path)
        self.assertNotIn("Fumehood", controls)


# --------------------------------------------------------------------------
# Nothing goes unassessed by accident
# --------------------------------------------------------------------------

class UnassessedTest(unittest.TestCase):

    def setUp(self):
        self.data = assessment()

    def test_pubchem_miss_is_carried_through_as_unknown(self):
        self.assertTrue(row_named(self.data, "ganymedene")["unknown"])

    def test_the_draft_page_shouts_about_it_at_the_top(self):
        body = webapp.draft_body(self.data)
        top = body[:body.index("<form")]
        self.assertIn("no classification", top.lower())
        self.assertIn("ganymedene", top)

    def test_typing_hazards_in_clears_the_banner_but_records_where_they_came_from(self):
        pairs = form_pairs(self.data, hazards_2="H302 - Harmful if swallowed")
        folded = fold(pairs)
        row = row_named(folded, "ganymedene")
        self.assertFalse(row["unknown"])
        self.assertEqual(row["hazards"], ["H302 - Harmful if swallowed"])
        self.assertTrue(any("typed in by hand" in line for line in folded["review"]),
                        "the form may show the chemist's codes, but the draft must say "
                        "they did not come from PubChem")

    def test_leaving_it_alone_keeps_the_loud_banner(self):
        row = row_named(fold(form_pairs(self.data)), "ganymedene")
        self.assertTrue(row["unknown"])

    def test_dropping_a_row_is_recorded_rather_than_silent(self):
        pairs = [(k, v) for k, v in form_pairs(self.data) if k != "include_2"]
        folded = fold(pairs)
        self.assertNotIn("ganymedene", [r["name"] for r in folded["substances"]])
        self.assertTrue(any("ganymedene" in line and "not assessed" in line
                            for line in folded["review"]))

    def test_a_form_with_no_substances_is_refused(self):
        pairs = [(k, v) for k, v in form_pairs(self.data)
                 if not k.startswith("include_")]
        with TestClient(webapp.app) as client:
            response = client.post("/document", data=as_data(pairs))
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("wordprocessingml", response.headers.get("content-type", ""))


# --------------------------------------------------------------------------
# The header is copied, never invented
# --------------------------------------------------------------------------

class HeaderTest(unittest.TestCase):

    def test_header_fields_are_taken_from_the_form_verbatim(self):
        data = assessment()
        pairs = form_pairs(data, title="Something else", college="Another College")
        folded = fold(pairs)
        self.assertEqual(folded["title"], "Something else")
        self.assertEqual(folded["college"], "Another College")

    def test_approved_by_is_not_a_field_anywhere_on_the_page(self):
        body = webapp.draft_body(assessment())
        self.assertNotIn("name=\"approved", body.lower())
        self.assertIn("blank", body.lower())


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

class RouteTest(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(webapp.app)

    def test_index_is_served(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])

    def test_index_says_it_is_a_draft_for_someone_else_to_sign(self):
        body = self.client.get("/").text
        self.assertIn("competent person", body)
        self.assertIn("Approved By", body)

    def test_index_says_nothing_is_stored(self):
        self.assertIn("Nothing is stored", self.client.get("/").text)

    def test_an_empty_paste_is_refused_before_any_model_call(self):
        response = self.client.post("/draft", data={"manual": "   "})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Nothing to read", response.text)

    def test_document_without_a_baseline_fails_cleanly(self):
        response = self.client.post("/document", data={"baseline": "not json"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("draft was lost", response.text)

    def test_document_returns_a_word_file_as_an_attachment(self):
        response = self.client.post("/document", data=as_data(form_pairs(assessment())))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["content-type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        self.assertIn("attachment", response.headers["content-disposition"])
        self.assertIn(".docx", response.headers["content-disposition"])
        self.assertTrue(response.content.startswith(b"PK"), "not a zip, so not a .docx")

    def test_the_document_is_not_cached(self):
        response = self.client.post("/document", data=as_data(form_pairs(assessment())))
        self.assertEqual(response.headers.get("cache-control"), "no-store")

    def test_nothing_is_left_on_disk(self):
        import glob
        import tempfile

        pattern = str(tempfile.gettempdir()) + "/coshh-*.docx"
        before = set(glob.glob(pattern))
        self.client.post("/document", data=as_data(form_pairs(assessment())))
        self.assertEqual(set(glob.glob(pattern)) - before, set())


# --------------------------------------------------------------------------
# Small things that would be ugly if they broke
# --------------------------------------------------------------------------

class RenderingTest(unittest.TestCase):

    def test_hazard_lines_match_what_the_writer_would_render(self):
        row = {"hazards": [{"code": "H225", "text": "Highly flammable liquid and vapour"}]}
        self.assertEqual(webapp.hazard_lines(row),
                         "H225 - Highly flammable liquid and vapour")

    def test_hazard_lines_accept_plain_strings_too(self):
        self.assertEqual(webapp.hazard_lines({"hazards": ["H302 - Harmful"]}),
                         "H302 - Harmful")

    def test_a_substance_name_cannot_inject_markup(self):
        data = assessment()
        data["substances"][0]["name"] = "<script>alert(1)</script>"
        body = webapp.draft_body(data)
        self.assertNotIn("<script>alert(1)</script>", body)
        self.assertIn("&lt;script&gt;", body)

    def test_the_baseline_survives_a_round_trip_through_the_page(self):
        import re

        data = assessment()
        body = webapp.draft_body(data)
        raw = re.search(r'name="baseline" value="([^"]*)"', body).group(1)
        import html as html_mod
        self.assertEqual(json.loads(html_mod.unescape(raw))["title"], data["title"])

    def test_every_waste_stream_the_rules_know_is_offered(self):
        body = webapp.draft_body(assessment())
        for stream in rules.WASTE_STREAMS:
            self.assertIn(stream, body)

    def test_every_control_measure_the_form_offers_is_on_the_page(self):
        body = webapp.draft_body(assessment())
        for control in docx_form.CONTROL_MEASURES:
            self.assertIn(control, body)

    def test_filename_is_built_from_the_title(self):
        self.assertEqual(webapp.filename_for({"title": "Nitration of toluene"}),
                         "COSHH-Nitration-of-toluene.docx")

    def test_filename_survives_a_hostile_title(self):
        name = webapp.filename_for({"title": "../../etc/passwd"})
        self.assertNotIn("/", name)
        self.assertTrue(name.endswith(".docx"))

    def test_filename_falls_back_when_there_is_no_title(self):
        self.assertEqual(webapp.filename_for({}), "COSHH-coshh.docx")


class UploadTest(unittest.TestCase):

    def test_plain_text_is_decoded(self):
        self.assertEqual(webapp.text_from_upload("m.txt", b"add 5 mL of water"),
                         "add 5 mL of water")

    def test_undecodable_bytes_do_not_crash_the_request(self):
        self.assertIsInstance(webapp.text_from_upload("m.txt", b"\xff\xfe abc"), str)

    def test_a_docx_upload_is_read_as_text(self):
        import io

        import docx

        document = docx.Document()
        document.add_paragraph("Dissolve 2 g of benzoic acid in 20 mL of ethanol.")
        buffer = io.BytesIO()
        document.save(buffer)
        text = webapp.text_from_upload("manual.docx", buffer.getvalue())
        self.assertIn("benzoic acid", text)
        self.assertIn("20 mL", text)


if __name__ == "__main__":
    unittest.main()
