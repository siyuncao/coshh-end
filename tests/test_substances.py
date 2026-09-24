"""
Reading a typed substance list, with PubChem stood in for.

Everything here is offline and nothing here costs anything — which is the point
of the module under test. `coshh.substances` is the path through the app that
needs no API key, so the first thing proved below is that importing it does not
so much as reach for the Anthropic SDK.

What is being pinned down:

* the awkward lines people actually type — `3 M HNO3 20 mL`, `2 x 25 mL` in
  brackets, `µL`, a range, a CAS number, a trailing remark — split the way a
  chemist would read them;
* an amount reaches the form character for character, because that is the field
  read back off the paper and compared with the balance;
* a line that cannot be split is never dropped: it keeps its place on the form
  with a blank amount, and it is named in the review list;
* a concentration is not an amount, so `0.5 M NaOH` does not become half a mole
  of hydroxide in the Amount cell;
* the assessment that comes out is the same shape `coshh.manual` produces, made
  by the same rule table, with no model anywhere in it.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coshh import rules, substances  # noqa: E402
from coshh.rules import FUMEHOOD, GLOVES, LAB_COAT, SPECTACLES, SPILL  # noqa: E402
from tests.test_manual import looker, pubchem  # noqa: E402


def parsed(line):
    """One line parsed, or a failed assertion if it was skipped outright."""
    entry = substances.parse_line(line)
    assert entry is not None, "{!r} was dropped".format(line)
    return entry


def split(line):
    """(name, amount) — the two things a reader checks first."""
    entry = parsed(line)
    return entry["name"], entry["amount"]


# --------------------------------------------------------------------------
# The lines people type
# --------------------------------------------------------------------------

class SplittingALine(unittest.TestCase):

    #: Fifteen lines off a real reagent list, awkward ones included.
    CASES = (
        ("pyrrolidine 7.11 g", "pyrrolidine", "7.11 g"),
        ("triethylamine, 15 mL", "triethylamine", "15 mL"),
        # The concentration belongs to the substance; the volume is the amount.
        ("3 M HNO3 20 mL", "3 M HNO3", "20 mL"),
        ("TEMPO 26.8 g (CAS 2564-83-2)", "TEMPO", "26.8 g"),
        ("dichloromethane (anhydrous) 5-10 mL", "dichloromethane (anhydrous)", "5-10 mL"),
        # The amount is inside the brackets and there is nothing after it.
        ("diethyl ether (2 x 25 mL)", "diethyl ether", "2 x 25 mL"),
        # One amount written twice. Both halves stay; neither is added up.
        ("toluene 5 mL (0.047 mol)", "toluene", "5 mL (0.047 mol)"),
        ("20 mL of 3 M HNO3", "3 M HNO3", "20 mL"),
        ("ethanol 30 mL, dried over MgSO4", "ethanol", "30 mL"),
        ("1. sodium borohydride (NaBH4) 1.2 g", "sodium borohydride (NaBH4)", "1.2 g"),
        ("- acetone ~50 µL", "acetone", "~50 µL"),
        ("conc. sulfuric acid 2 drops", "conc. sulfuric acid", "2 drops"),
        ("ethyl acetate | 100 mL", "ethyl acetate", "100 mL"),
        ("N,N-dimethylformamide (DMF): 3 mL", "N,N-dimethylformamide (DMF)", "3 mL"),
        ("sodium chloride 0.9% 10 mL", "sodium chloride 0.9%", "10 mL"),
        ("lithium aluminium hydride 0.45 g (CAS 16853-85-3)",
         "lithium aluminium hydride", "0.45 g"),
        ("silica gel", "silica gel", ""),
        # Molarity is what is in the bottle, not how much is being used.
        ("0.5 M NaOH", "0.5 M NaOH", ""),
    )

    def test_every_line_splits_the_way_a_chemist_reads_it(self):
        for line, name, amount in self.CASES:
            with self.subTest(line=line):
                self.assertEqual(split(line), (name, amount))

    def test_at_least_fifteen_of_them(self):
        """A guard on the fixture itself, not on the parser."""
        self.assertGreaterEqual(len(self.CASES), 15)

    def test_the_raw_line_is_kept_with_every_entry(self):
        entry = parsed("  1. sodium borohydride (NaBH4) 1.2 g  ")
        self.assertEqual(entry["raw"], "1. sodium borohydride (NaBH4) 1.2 g")
        # `source_line` is what the review page quotes back, so it is the line
        # as typed and not the parser's reading of it.
        self.assertEqual(entry["source_line"], entry["raw"])

    def test_the_amount_is_transcribed_not_converted(self):
        for line, amount in (("acetone 2 x 20 mL", "2 x 20 mL"),
                             ("water 5-10 mL", "5-10 mL"),
                             ("DMSO ~0,5 mL", "~0,5 mL"),
                             ("methanol 5 to 10 mL", "5 to 10 mL"),
                             ("hexane 1.5 L", "1.5 L")):
            with self.subTest(line=line):
                self.assertEqual(parsed(line)["amount"], amount)

    def test_micro_survives_in_either_spelling(self):
        for micro in ("µ", "μ"):           # MICRO SIGN, GREEK SMALL MU
            with self.subTest(micro=micro):
                entry = parsed("acetonitrile 250 {}L".format(micro))
                self.assertEqual(entry["name"], "acetonitrile")
                self.assertEqual(entry["amount"], "250 {}L".format(micro))

    def test_a_bracketed_remark_does_not_reach_the_amount(self):
        entry = parsed("ethanol 30 mL, dried over MgSO4")
        self.assertEqual(entry["amount"], "30 mL")
        self.assertIn("dried over MgSO4", entry["role"])

    def test_a_concentration_is_never_read_as_an_amount(self):
        for line in ("0.5 M NaOH", "HCl 2 M", "hydrogen peroxide 30% w/w",
                     "sodium hydroxide 0.5 mol/L"):
            with self.subTest(line=line):
                self.assertEqual(parsed(line)["amount"], "")


class TheCASNumber(unittest.TestCase):

    def test_a_cas_number_is_taken_off_the_line(self):
        entry = parsed("TEMPO 26.8 g (CAS 2564-83-2)")
        self.assertEqual(entry["cas"], "2564-83-2")
        self.assertNotIn("2564", entry["name"])

    def test_a_bare_cas_number_is_taken_too(self):
        self.assertEqual(parsed("acetone 50 mL (67-64-1)")["cas"], "67-64-1")

    def test_a_number_that_fails_its_check_digit_is_not_a_cas_number(self):
        """`1,3-propanediol 5-10 g` has a CAS-shaped token in it and no CAS number."""
        entry = parsed("1,3-propanediol 5-10 g")
        self.assertEqual(entry["cas"], "")
        self.assertEqual(entry["name"], "1,3-propanediol")
        self.assertEqual(entry["amount"], "5-10 g")

    def test_a_labelled_cas_number_is_kept_but_flagged_when_it_does_not_check_out(self):
        entry = parsed("mystery compound 1 g (CAS 2564-83-3)")
        self.assertEqual(entry["cas"], "2564-83-3")
        self.assertIn("check digit", entry["parse_note"])


class TheSearchTerm(unittest.TestCase):
    """`lookup_name` is what PubChem is asked; `name` is what the form says."""

    def test_grade_and_strength_come_off_the_search_term_only(self):
        for line, name, search in (
                ("conc. sulfuric acid 2 drops", "conc. sulfuric acid", "sulfuric acid"),
                ("3 M HNO3 20 mL", "3 M HNO3", "HNO3"),
                ("dichloromethane (anhydrous) 5 mL", "dichloromethane (anhydrous)",
                 "dichloromethane"),
                ("saturated aqueous sodium bicarbonate 50 mL",
                 "saturated aqueous sodium bicarbonate", "sodium bicarbonate")):
            with self.subTest(line=line):
                entry = parsed(line)
                self.assertEqual(entry["name"], name)
                self.assertEqual(entry["lookup_name"], search)

    def test_a_plain_name_gets_no_second_search_term(self):
        self.assertEqual(parsed("pyrrolidine 7.11 g")["lookup_name"], "")

    def test_stripping_never_turns_one_substance_into_another(self):
        """Dry ice is not ice. PubChem answers 'ice' with water."""
        self.assertEqual(parsed("dry ice")["lookup_name"], "")


# --------------------------------------------------------------------------
# Nothing is ever dropped
# --------------------------------------------------------------------------

class NothingIsDropped(unittest.TestCase):

    def test_a_line_with_no_amount_is_still_a_substance(self):
        entry = parsed("silica gel")
        self.assertEqual(entry["name"], "silica gel")
        self.assertEqual(entry["amount"], "")

    def test_a_line_that_is_only_an_amount_keeps_its_text_as_the_name(self):
        entry = parsed("5 g")
        self.assertEqual(entry["name"], "5 g")
        self.assertEqual(entry["amount"], "")
        self.assertIn("no substance name", entry["parse_note"])

    def test_only_a_line_with_no_letter_and_no_digit_is_skipped(self):
        for blank in ("", "   ", "-----", "\t", " , "):
            with self.subTest(blank=blank):
                self.assertIsNone(substances.parse_line(blank))

    def test_every_other_line_survives_the_whole_list(self):
        entries = substances.parse_list(
            "pyrrolidine 7.11 g\n"
            "\n"
            "-----\n"
            "Reagents:\n"
            "5 g\n"
            "water\n")
        self.assertEqual([e["name"] for e in entries],
                         ["pyrrolidine", "Reagents", "5 g", "water"])

    def test_a_blank_amount_earns_a_line_in_the_review(self):
        notes = substances.notes_for(substances.parse_list("pyrrolidine 7.11 g\nwater\n"))
        self.assertEqual(len(notes), 1)
        self.assertIn("water", notes[0])
        self.assertIn("'water'", notes[0])

    def test_an_unreadable_line_says_which_line_it_was(self):
        notes = substances.notes_for(substances.parse_list("5 g\n"))
        self.assertEqual(len(notes), 1)
        self.assertIn("'5 g'", notes[0])
        self.assertIn("blank Amount", notes[0])

    def test_an_empty_box_is_refused_rather_than_assessed(self):
        for text in ("", "   \n\n", "----\n"):
            with self.subTest(text=text):
                with self.assertRaises(substances.NothingToList):
                    substances.parse_list(text)

    def test_a_pasted_catalogue_is_refused_rather_than_truncated(self):
        with self.assertRaises(substances.ListTooLong):
            substances.parse_list("acetone 5 mL\n" * (substances.MAX_LIST_LINES + 1))
        with self.assertRaises(substances.ListTooLong):
            substances.parse_list("x" * (substances.MAX_LIST_CHARS + 1))


class TheExtractorShape(unittest.TestCase):
    """`read_list` stands in for `manual.extract`, so it has to match it."""

    def test_it_returns_the_shape_the_reader_returns(self):
        read = substances.read_list("pyrrolidine 7.11 g")
        self.assertEqual(set(read) - {"notes"}, {"scheme", "substances", "equipment"})
        self.assertEqual(read["equipment"], [])
        # A reagent list says nothing about the reaction, so the scheme is
        # empty and `manual.assess` writes its own "draw it in by hand".
        self.assertEqual(read["scheme"], "")

    def test_every_field_the_reader_produces_is_present(self):
        from coshh import manual

        entry = substances.parse_line("pyrrolidine 7.11 g")
        for field in manual._SUBSTANCE_FIELDS:
            with self.subTest(field=field):
                self.assertIn(field, entry)


# --------------------------------------------------------------------------
# The whole path, offline
# --------------------------------------------------------------------------

LIST = ("pyrrolidine 7.11 g\n"
        "triethylamine, 15 mL\n"
        "dichloromethane (anhydrous) 50 mL\n"
        "silica gel\n")

LOOKUP = {
    "pyrrolidine": pubchem("pyrrolidine", "H225", "H302", "H314", "H332"),
    "triethylamine": pubchem("triethylamine", "H225", "H302", "H311", "H314", "H332"),
    "dichloromethane": pubchem("dichloromethane", "H315", "H319", "H336", "H351"),
    "silica gel": pubchem("silica gel", found=False, cid=24261),
}


def assessed(text=LIST, **overrides):
    fields = dict(title="Amide coupling", name="A Chemist", date="2026-09-24",
                  college="Department", year="2", lookup=looker(LOOKUP))
    fields.update(overrides)
    return substances.assess(text, **fields)


class TheWholePath(unittest.TestCase):

    def setUp(self):
        self.data = assessed()
        self.rows = {row["name"]: row for row in self.data["substances"]}

    def test_a_row_per_line_in_the_order_they_were_typed(self):
        self.assertEqual([row["name"] for row in self.data["substances"]],
                         ["pyrrolidine", "triethylamine",
                          "dichloromethane (anhydrous)", "silica gel"])

    def test_the_amounts_reach_the_rows_untouched(self):
        self.assertEqual(self.rows["pyrrolidine"]["amount"], "7.11 g")
        self.assertEqual(self.rows["triethylamine"]["amount"], "15 mL")
        self.assertEqual(self.rows["silica gel"]["amount"], "")

    def test_the_rule_table_is_applied_not_the_parser(self):
        """The ticks come from the H codes, exactly as the manual path's do."""
        row = self.rows["pyrrolidine"]
        self.assertIn("H314", row["codes"])
        for control in (SPILL, SPECTACLES, LAB_COAT, GLOVES, FUMEHOOD):
            with self.subTest(control=control):
                self.assertIn(control, row["controls"])

    def test_an_unclassified_substance_is_shouted_about_not_left_clean(self):
        row = self.rows["silica gel"]
        self.assertTrue(row["unknown"])
        self.assertTrue(row["needs_review"])
        self.assertTrue(any("silica gel" in line for line in self.data["review"]))

    def test_the_search_term_is_reported_when_it_differs_from_the_row(self):
        self.assertTrue(any("dichloromethane" in line and "looked up" in line
                            for line in self.data["review"]))

    def test_a_blank_amount_is_at_the_top_of_the_review(self):
        self.assertIn("silica gel", self.data["review"][0])
        self.assertIn("no amount", self.data["review"][0])

    def test_no_model_was_used_and_the_dict_says_so(self):
        self.assertEqual(self.data["model"], substances.NO_MODEL)
        self.assertIn("no model call", self.data["model"])

    def test_the_header_is_copied_and_never_invented(self):
        self.assertEqual(self.data["title"], "Amide coupling")
        self.assertEqual(self.data["college"], "Department")
        self.assertEqual(self.data["year"], "2")

    def test_a_blank_header_field_is_reported_rather_than_filled_in(self):
        data = assessed(title="", name="", date="", college="", year="")
        self.assertEqual(data["title"], "")
        self.assertTrue(any("Header left blank" in line for line in data["review"]))

    def test_the_draft_always_needs_a_human(self):
        self.assertTrue(self.data["needs_review"])
        self.assertTrue(any("Approved By" in line for line in self.data["review"]))

    def test_the_same_substance_twice_is_one_row_with_both_amounts(self):
        data = assessed("pyrrolidine 7.11 g\npyrrolidine 2 mL\n")
        self.assertEqual([row["name"] for row in data["substances"]], ["pyrrolidine"])
        self.assertEqual(data["substances"][0]["amount"], "7.11 g; 2 mL")

    def test_it_produces_what_the_manual_path_produces(self):
        """Same keys, same types — `/draft` and `/document` cannot tell them apart."""
        from tests import test_app

        self.assertEqual(set(self.data), set(test_app.assessment()))

    def test_the_waste_streams_come_out_of_the_rule_table(self):
        self.assertTrue(set(self.data["waste"]) <= set(rules.WASTE_STREAMS))
        self.assertIn(rules.HALOGENATED, self.data["waste"])


# --------------------------------------------------------------------------
# The promise that makes this the default path
# --------------------------------------------------------------------------

class NoKeyAndNoNetwork(unittest.TestCase):

    def test_the_module_names_no_anthropic_anything(self):
        import inspect

        source = inspect.getsource(substances)
        self.assertNotIn("anthropic", source.lower().replace("no model call", ""))

    def test_it_imports_and_parses_with_no_key_in_the_environment(self):
        """A fresh import, no `ANTHROPIC_API_KEY`, no SDK loaded, no socket used."""
        import importlib
        import socket

        saved = os.environ.pop("ANTHROPIC_API_KEY", None)
        had_sdk = "anthropic" in sys.modules
        real_socket = socket.socket

        def no_network(*args, **kwargs):
            raise AssertionError("the substance list path opened a socket")

        socket.socket = no_network
        try:
            module = importlib.reload(substances)
            self.assertEqual(module.parse_line("pyrrolidine 7.11 g")["amount"], "7.11 g")
            data = module.assess("pyrrolidine 7.11 g", lookup=looker(LOOKUP))
            self.assertEqual(data["substances"][0]["name"], "pyrrolidine")
            if not had_sdk:
                self.assertNotIn("anthropic", sys.modules)
        finally:
            socket.socket = real_socket
            if saved is not None:
                os.environ["ANTHROPIC_API_KEY"] = saved
            importlib.reload(substances)


# --------------------------------------------------------------------------
# The two routes, with PubChem stood in for
#
# These live here rather than in `tests/test_app.py` because what they are
# checking is this module's promise: that the default way through the app asks
# nobody for a key.
# --------------------------------------------------------------------------

class TheDefaultPathThroughTheApp(unittest.TestCase):

    def setUp(self):
        import safety
        from fastapi.testclient import TestClient

        import app as webapp

        self.client = TestClient(webapp.app)
        self.saved_key = os.environ.pop("ANTHROPIC_API_KEY", None)
        self.real_hazards = safety.hazards
        safety.hazards = looker(LOOKUP)
        self.safety = safety

    def tearDown(self):
        self.safety.hazards = self.real_hazards
        if self.saved_key is not None:
            os.environ["ANTHROPIC_API_KEY"] = self.saved_key

    def test_the_front_page_asks_for_the_list_before_the_manual(self):
        body = self.client.get("/").text
        self.assertIn("name=\"substances\"", body)
        self.assertLess(body.index("name=\"substances\""), body.index("name=\"manual\""))

    def test_a_list_is_drafted_with_no_key_anywhere(self):
        response = self.client.post("/draft", data={
            "substances": LIST, "title": "Amide coupling", "name": "A Chemist",
            "date": "2026-09-24", "college": "Department", "year": "2"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("pyrrolidine", response.text)
        self.assertIn("7.11 g", response.text)
        self.assertNotIn("needs an Anthropic API key", response.text)

    def test_a_list_and_a_procedure_together_are_refused_not_half_assessed(self):
        response = self.client.post("/draft", data={
            "substances": "acetone 5 mL", "manual": "To a stirred solution of ..."})
        self.assertIn("Two different inputs", response.text)

    def test_an_empty_list_is_refused(self):
        response = self.client.post("/draft", data={"substances": "   \n  "})
        self.assertIn("Nothing to", response.text)


if __name__ == "__main__":
    unittest.main()
