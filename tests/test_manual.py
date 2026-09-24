"""
Reading a lab manual into an assessment, with the model and PubChem stood in for.

Everything here is offline. The two things this module talks to — the Anthropic
API and PubChem — are injected, so these tests say what `coshh.manual` does with
an answer, not whether the answer arrives. The live check is at the bottom,
skipped unless COSHH_LIVE is set, because a test suite that costs money and
needs a network is a test suite people stop running.

What is being pinned down:

* an amount reaches the form character for character — this is the field a
  chemist reads back off the paper and compares with the balance;
* a substance PubChem cannot classify still gets a row, in capitals, in the
  review list — never a quiet omission;
* the rule table is actually applied, rather than the model's opinion of it;
* a substance the model judged unused is listed, not deleted;
* equipment does not get treated as an unclassified chemical.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coshh import manual, rules  # noqa: E402
from coshh.rules import (  # noqa: E402
    ADD_DROPWISE, FIRE, FUMEHOOD, GLOVES, HALOGENATED, LAB_COAT, NAMED_WASTE,
    NO_FLAMES, SPECIAL, SPECTACLES, SPILL,
)


# --------------------------------------------------------------------------
# Stand-ins
# --------------------------------------------------------------------------

def pubchem(name, *codes, cas="", found=True):
    """The shape `safety.hazards()` returns, trimmed to the fields rules reads."""
    return {
        "found": found,
        "cid": 1140 if found else None,
        "name": name,
        "cas": cas,
        "url": "https://pubchem.ncbi.nlm.nih.gov/compound/1140" if found else None,
        "primary": {
            "source": "Regulation (EC) No 1272/2008",
            "signal_word": "Danger",
            "pictograms": [],
            "hazards": [{"code": c,
                         "text": rules.RULES[c].wording if c in rules.RULES else "",
                         "classification": None, "agreement": None}
                        for c in codes],
            "precautions": [],
        } if found else None,
        "other_sources": [],
        "note": None if found else "PubChem holds no GHS classification for this one.",
    }


def extractor(scheme="", substances=(), equipment=()):
    """An `extract` that returns a fixed reading, ignoring the text."""
    def fake(text, *, client=None, model=manual.MODEL):
        return {"scheme": scheme,
                "substances": [dict(s) for s in substances],
                "equipment": [dict(e) for e in equipment]}
    return fake


def substance(name, amount="", *, cas="", formula="", role="reagent", used=True,
              lookup_name="", source_line="from the method"):
    return {"name": name, "lookup_name": lookup_name, "cas": cas, "formula": formula,
            "amount": amount, "role": role, "used": used, "source_line": source_line}


def looker(table):
    """A `safety.hazards` that answers from a {name: result} dict."""
    def fake(name, cas=""):
        return table.get(name, pubchem(name, found=False, cas=cas))
    return fake


def row_for(assessment, name):
    for row in assessment["substances"]:
        if row["name"] == name:
            return row
    raise AssertionError(f"{name} has no row: {[r['name'] for r in assessment['substances']]}")


# --------------------------------------------------------------------------
# The promise that matters most: the number on the form is the number in the text
# --------------------------------------------------------------------------

class AmountTest(unittest.TestCase):
    """An amount is transcribed, never parsed, converted or tidied."""

    VERBATIM = [
        "2.12 g, 20 mmol",
        "30 mL",
        "3 M, 20 mL",
        "0.5 equiv.",
        "1.0 g (6.5 mmol, 1.1 eq)",
        "~5 drops",
        "2 × 25 mL",
    ]

    def test_amount_reaches_the_row_character_for_character(self):
        for amount in self.VERBATIM:
            with self.subTest(amount=amount):
                out = manual.assess(
                    "method", extractor=extractor(substances=[substance("toluene", amount)]),
                    lookup=looker({"toluene": pubchem("toluene", "H225", "H304")}))
                self.assertEqual(row_for(out, "toluene")["amount"], amount)

    def test_two_additions_are_kept_apart_not_added_up(self):
        out = manual.assess(
            "method",
            extractor=extractor(substances=[
                substance("ethanol", "30 mL", source_line="dissolved in ethanol (30 mL)"),
                substance("ethanol", "a further 10 mL", source_line="washed with 10 mL"),
            ]),
            lookup=looker({"ethanol": pubchem("ethanol", "H225")}))
        rows = [r for r in out["substances"] if r["name"] == "ethanol"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["amount"], "30 mL; a further 10 mL")
        self.assertNotIn("40", rows[0]["amount"])

    def test_no_amount_stays_empty_rather_than_becoming_a_guess(self):
        out = manual.assess(
            "method", extractor=extractor(substances=[substance("celite")]),
            lookup=looker({}))
        self.assertEqual(row_for(out, "celite")["amount"], "")


# --------------------------------------------------------------------------
# Nothing goes missing
# --------------------------------------------------------------------------

class NothingSilentlyDroppedTest(unittest.TestCase):

    def test_substance_pubchem_cannot_classify_still_gets_a_loud_row(self):
        out = manual.assess(
            "method",
            extractor=extractor(substances=[substance("ethyl 4-oxo-hexanoate", "1.2 g")]),
            lookup=looker({}))
        row = row_for(out, "ethyl 4-oxo-hexanoate")
        self.assertFalse(row["classified"])
        self.assertIn("NO CLASSIFICATION FOUND", row["hazards_text"])
        self.assertTrue(row["unknown"])
        self.assertEqual(row["amount"], "1.2 g")
        self.assertTrue(row["needs_review"])
        self.assertTrue(any("ethyl 4-oxo-hexanoate" in line for line in out["review"]))
        self.assertTrue(out["needs_review"])

    def test_unclassified_row_ticks_more_than_a_blank_row_does(self):
        out = manual.assess(
            "method", extractor=extractor(substances=[substance("mystery solid")]),
            lookup=looker({}))
        controls = row_for(out, "mystery solid")["controls"]
        self.assertEqual(controls, [SPILL, SPECTACLES, LAB_COAT, GLOVES, FUMEHOOD])

    def test_unclassified_row_assumes_every_route(self):
        out = manual.assess(
            "method", extractor=extractor(substances=[substance("mystery solid")]),
            lookup=looker({}))
        self.assertEqual(row_for(out, "mystery solid")["exposure"],
                         list(rules.EXPOSURE_ROUTES))

    def test_mentioned_but_unused_is_listed_and_explained_not_deleted(self):
        out = manual.assess(
            "method",
            extractor=extractor(substances=[
                substance("toluene", "20 mL"),
                substance("benzene", used=False,
                          source_line="the original synthesis used benzene"),
            ]),
            lookup=looker({"toluene": pubchem("toluene", "H225")}))
        self.assertEqual([r["name"] for r in out["substances"]], ["toluene"])
        self.assertEqual([s["name"] for s in out["mentioned_not_used"]], ["benzene"])
        self.assertTrue(any("benzene" in line and "not used" in line
                            for line in out["review"]))

    def test_unrecognised_waste_goes_to_named_waste_and_to_review(self):
        out = manual.assess(
            "method", extractor=extractor(substances=[substance("mystery solid")]),
            lookup=looker({}))
        self.assertIn(NAMED_WASTE, out["waste"])
        self.assertTrue(any("mystery solid" in line and "label" in line.lower()
                            for line in out["review"]))


# --------------------------------------------------------------------------
# The rules are the rules module's, applied — not the model's
# --------------------------------------------------------------------------

class LookupNameTest(unittest.TestCase):
    """The row keeps the procedure's words; only the database search is tidied."""

    def setUp(self):
        self.searched = []

        def watching(name, cas=""):
            self.searched.append(name)
            return pubchem(name, "H272", "H290", "H314", cas=cas)

        self.out = manual.assess(
            "method",
            extractor=extractor(substances=[
                substance("concentrated nitric acid", "1.5 mL",
                          lookup_name="nitric acid")]),
            lookup=watching)

    def test_pubchem_is_asked_for_the_plain_name(self):
        self.assertEqual(self.searched, ["nitric acid"])

    def test_the_row_still_reads_what_the_procedure_wrote(self):
        row = row_for(self.out, "concentrated nitric acid")
        self.assertEqual(row["amount"], "1.5 mL")
        self.assertTrue(row["classified"])

    def test_the_substitution_is_declared_not_hidden(self):
        self.assertTrue(any("concentrated nitric acid" in line and "nitric acid" in line
                            for line in self.out["review"]))

    def test_a_redundant_lookup_name_is_dropped(self):
        read = manual.extract("text", client=_Client(json.dumps({
            "scheme": "", "equipment": [],
            "substances": [{"name": "Toluene", "lookup_name": "toluene", "cas": "",
                            "formula": "", "amount": "", "role": "", "used": True,
                            "source_line": ""}]})))
        self.assertEqual(read["substances"][0]["lookup_name"], "")


class RulesAreAppliedTest(unittest.TestCase):

    def assess_dcm_and_sodium_borohydride(self):
        return manual.assess(
            "Add sodium borohydride portionwise to the solution.",
            extractor=extractor(substances=[
                substance("dichloromethane", "50 mL", formula="CH2Cl2", role="solvent"),
                substance("sodium borohydride", "0.95 g, 25 mmol"),
            ]),
            lookup=looker({
                "dichloromethane": pubchem("dichloromethane", "H315", "H319", "H336", "H351"),
                "sodium borohydride": pubchem(
                    "sodium borohydride", "H260", "H301", "H311", "H314", "H318",
                    "H332", "H360"),
            }))

    def test_exposure_routes_come_from_the_codes(self):
        out = self.assess_dcm_and_sodium_borohydride()
        routes = set(row_for(out, "sodium borohydride")["exposure"])
        self.assertEqual(routes, set(rules.EXPOSURE_ROUTES))

    def test_controls_match_what_the_rule_table_says(self):
        out = self.assess_dcm_and_sodium_borohydride()
        controls = set(row_for(out, "sodium borohydride")["controls"])
        for option in (SPILL, SPECTACLES, LAB_COAT, GLOVES, FUMEHOOD,
                       rules.NOT_NEAR_WATER, rules.NOT_IF_PREGNANT):
            self.assertIn(option, controls)

    def test_every_tick_carries_its_reason(self):
        out = self.assess_dcm_and_sodium_borohydride()
        row = row_for(out, "sodium borohydride")
        self.assertEqual(sorted(row["controls"]), sorted(row["controls_why"]))
        self.assertEqual(sorted(row["exposure"]), sorted(row["exposure_why"]))
        self.assertTrue(all(row["controls_why"][c].strip() for c in row["controls"]))

    def test_hazard_text_quotes_the_published_codes(self):
        out = self.assess_dcm_and_sodium_borohydride()
        row = row_for(out, "dichloromethane")
        self.assertEqual([h["code"] for h in row["hazards"]],
                         ["H315", "H319", "H336", "H351"])
        self.assertTrue(all(h["text"].strip() for h in row["hazards"]))
        for code in ("H315", "H319", "H336", "H351"):
            self.assertIn(code, row["hazards_text"])

    def test_ticks_are_returned_in_the_templates_own_order(self):
        out = self.assess_dcm_and_sodium_borohydride()
        row = row_for(out, "sodium borohydride")
        order = list(rules.CONTROL_MEASURES)
        self.assertEqual(row["controls"], [c for c in order if c in row["controls"]])
        self.assertEqual(row["exposure"],
                         [r for r in rules.EXPOSURE_ROUTES if r in row["exposure"]])

    def test_a_halogenated_solvent_fills_the_halogenated_bottle(self):
        out = self.assess_dcm_and_sodium_borohydride()
        self.assertIn(HALOGENATED, out["waste"])
        self.assertTrue(out["waste_why"][HALOGENATED])

    def test_waste_is_in_the_templates_order(self):
        out = self.assess_dcm_and_sodium_borohydride()
        self.assertEqual(out["waste"],
                         [s for s in rules.WASTE_STREAMS if s in out["waste"]])

    def test_all_five_risk_rows_are_answered_even_the_nos(self):
        out = manual.assess(
            "method", extractor=extractor(substances=[substance("water", "10 mL")]),
            lookup=looker({"water": pubchem("water", found=False)}))
        self.assertEqual(list(out["implications"]), list(rules.RISK_ROWS))
        for row, value in out["implications"].items():
            self.assertTrue(value["why"].strip(), row)

    def test_a_flammable_solvent_ticks_fire(self):
        out = manual.assess(
            "method", extractor=extractor(substances=[substance("diethyl ether", "100 mL")]),
            lookup=looker({"diethyl ether": pubchem("diethyl ether", "H224")}))
        self.assertTrue(out["implications"][FIRE]["yes"])
        self.assertTrue(out["implications"][FIRE]["prevention"].strip())
        self.assertIn(NO_FLAMES, row_for(out, "diethyl ether")["controls"])

    def test_special_measures_is_left_for_the_chemist(self):
        out = self.assess_dcm_and_sodium_borohydride()
        self.assertFalse(out["implications"][SPECIAL]["yes"])
        self.assertEqual(out["implications"][SPECIAL]["prevention"], "")

    def test_the_procedure_text_reaches_the_rules(self):
        """'add dropwise' in a substance's own sentence must tick its dropwise box."""
        out = manual.assess(
            "Add the acid dropwise to the stirred solution over 10 minutes.",
            extractor=extractor(substances=[substance(
                "acetic acid", "5 mL",
                source_line="Add the acid dropwise to the stirred solution over 10 minutes.")]),
            lookup=looker({"acetic acid": pubchem("acetic acid", "H226", "H314")}))
        self.assertIn(ADD_DROPWISE, row_for(out, "acetic acid")["controls"])

    def test_a_method_level_control_does_not_land_on_an_unrelated_row(self):
        """'Add dropwise' next to the drying oven is how a form stops being read."""
        out = manual.assess(
            "Add the acid dropwise over 10 minutes. The solid was dried in the oven.",
            extractor=extractor(substances=[
                substance("acetic acid", "5 mL", source_line="Add the acid dropwise over 10 minutes."),
                substance("sodium sulfate", "2 g", source_line="The solid was dried in the oven.")]),
            lookup=looker({"acetic acid": pubchem("acetic acid", "H226"),
                           "sodium sulfate": pubchem("sodium sulfate", "H319")}))
        self.assertIn(ADD_DROPWISE, row_for(out, "acetic acid")["controls"])
        self.assertNotIn(ADD_DROPWISE, row_for(out, "sodium sulfate")["controls"])

    def test_approval_is_never_filled_and_is_always_flagged(self):
        out = manual.assess(
            "method", extractor=extractor(substances=[substance("water")]),
            lookup=looker({}))
        self.assertNotIn("approved_by", out)
        self.assertTrue(any("Approved By" in line for line in out["review"]))


# --------------------------------------------------------------------------
# Equipment is not a chemical
# --------------------------------------------------------------------------

class EquipmentTest(unittest.TestCase):

    def setUp(self):
        self.out = manual.assess(
            "Heat the flask in an oil bath at 110 °C.",
            extractor=extractor(
                substances=[substance("toluene", "20 mL")],
                equipment=[{"name": "oil bath", "note": "heated to 110 °C",
                            "source_line": "Heat the flask in an oil bath at 110 °C."}]),
            lookup=looker({"toluene": pubchem("toluene", "H225")}))

    def test_equipment_gets_a_row_of_its_own_kind(self):
        row = row_for(self.out, "oil bath")
        self.assertEqual(row["kind"], "equipment")
        self.assertEqual(row["amount"], "")
        self.assertEqual(row["codes"], [])

    def test_equipment_is_not_pretended_to_have_a_classification(self):
        row = row_for(self.out, "oil bath")
        self.assertIn("EQUIPMENT", row["note"])
        self.assertEqual(row["hazards"], [])
        self.assertFalse(row["unknown"])
        self.assertTrue(row["needs_review"])

    def test_equipment_does_not_go_into_a_waste_bottle(self):
        self.assertFalse(any("oil bath" in why for why in self.out["waste_why"].values()))

    def test_equipment_keeps_the_standing_controls(self):
        for option in (SPILL, SPECTACLES, LAB_COAT):
            self.assertIn(option, row_for(self.out, "oil bath")["controls"])


# --------------------------------------------------------------------------
# The header belongs to the caller
# --------------------------------------------------------------------------

class HeaderTest(unittest.TestCase):

    def assess(self, **header):
        return manual.assess("method",
                             extractor=extractor(substances=[substance("water")]),
                             lookup=looker({}), **header)

    def test_header_fields_are_copied_not_invented(self):
        out = self.assess(title="Nitration of toluene", name="S. Cao",
                          date="24/09/2026", college="Univ", year="2")
        self.assertEqual(out["title"], "Nitration of toluene")
        self.assertEqual(out["name"], "S. Cao")
        self.assertEqual(out["date"], "24/09/2026")
        self.assertEqual(out["college"], "Univ")
        self.assertEqual(out["year"], "2")

    def test_a_missing_header_stays_missing_and_is_reported(self):
        out = self.assess(title="Nitration")
        self.assertEqual(out["date"], "")
        line = next(l for l in out["review"] if l.startswith("Header left blank"))
        for field in ("name", "date", "college", "year"):
            self.assertIn(field, line)
        self.assertNotIn("title", line)

    def test_a_year_the_form_does_not_offer_is_refused_not_coerced(self):
        out = self.assess(year="4")
        self.assertEqual(out["year"], "")
        self.assertTrue(any("1 / 2 / 3" in line for line in out["review"]))

    def test_no_scheme_in_the_text_says_so(self):
        out = self.assess()
        self.assertIn("Draw the scheme in by hand", out["scheme_note"])

    def test_a_scheme_is_quoted_and_still_asks_for_the_drawing(self):
        out = manual.assess(
            "method",
            extractor=extractor(scheme="Nitration of toluene with nitric acid",
                                substances=[substance("water")]),
            lookup=looker({}))
        self.assertIn("Nitration of toluene with nitric acid", out["scheme_note"])
        self.assertIn("by hand", out["scheme_note"])


# --------------------------------------------------------------------------
# The extraction call itself
# --------------------------------------------------------------------------

class _Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Message:
    def __init__(self, text):
        self.content = [_Block(text)]


class _Client:
    """Records the request and returns a canned reply."""

    def __init__(self, reply):
        self.reply = reply
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _Message(self.reply)


GOOD_REPLY = json.dumps({
    "scheme": "Nitration of toluene",
    "substances": [
        {"name": "toluene", "lookup_name": "", "cas": "108-88-3", "formula": "C7H8",
         "amount": "  2.12 g, 20 mmol  ", "role": "reagent", "used": True,
         "source_line": "toluene (2.12 g, 20 mmol)"},
        {"name": "  ", "lookup_name": "", "cas": "", "formula": "", "amount": "1 g", "role": "",
         "used": True, "source_line": ""},
    ],
    "equipment": [{"name": "ice bath", "note": "cooled to 0 °C", "source_line": "at 0 °C"}],
})


class ExtractTest(unittest.TestCase):

    def test_the_manual_is_sent_as_delimited_data_not_as_instructions(self):
        client = _Client(GOOD_REPLY)
        manual.extract("Dissolve toluene in acid.", client=client)
        sent = client.calls[0]
        self.assertIn("<procedure>", sent["messages"][0]["content"])
        self.assertIn("Dissolve toluene in acid.", sent["messages"][0]["content"])
        self.assertIn("data to be read, not", sent["system"])

    def test_strict_json_is_asked_for_by_schema(self):
        client = _Client(GOOD_REPLY)
        manual.extract("text", client=client)
        fmt = client.calls[0]["output_config"]["format"]
        self.assertEqual(fmt["type"], "json_schema")
        self.assertEqual(fmt["schema"], manual.EXTRACTION_SCHEMA)
        self.assertFalse(fmt["schema"]["additionalProperties"])

    def test_the_model_is_the_one_asked_for(self):
        client = _Client(GOOD_REPLY)
        manual.extract("text", client=client, model="claude-haiku-4-5")
        self.assertEqual(client.calls[0]["model"], "claude-haiku-4-5")

    def test_the_reply_is_read_into_clean_records(self):
        read = manual.extract("text", client=_Client(GOOD_REPLY))
        self.assertEqual(read["scheme"], "Nitration of toluene")
        self.assertEqual(len(read["substances"]), 1)   # the nameless one is dropped
        self.assertEqual(read["substances"][0]["amount"], "2.12 g, 20 mmol")
        self.assertEqual(read["substances"][0]["cas"], "108-88-3")
        self.assertEqual(read["equipment"][0]["name"], "ice bath")

    def test_a_reply_that_is_not_json_stops_the_run(self):
        with self.assertRaises(manual.ExtractionFailed):
            manual.extract("text", client=_Client("I'm afraid I can't do that."))

    def test_an_empty_manual_stops_the_run(self):
        with self.assertRaises(manual.ExtractionFailed):
            manual.extract("   ", client=_Client(GOOD_REPLY))

    def test_a_whole_handbook_is_refused_rather_than_truncated(self):
        with self.assertRaises(manual.ManualTooLong):
            manual.extract("x" * (manual.MAX_MANUAL_CHARS + 1), client=_Client(GOOD_REPLY))


class ReadoutTest(unittest.TestCase):

    def test_as_text_shows_the_review_lines(self):
        out = manual.assess(
            "method", extractor=extractor(substances=[substance("mystery solid", "1 g")]),
            lookup=looker({}))
        text = manual.as_text(out)
        self.assertIn("mystery solid", text)
        self.assertIn("1 g", text)
        self.assertIn("CHECK BEFORE SIGNING", text)
        self.assertIn("NEEDS REVIEW", text)


# --------------------------------------------------------------------------
# The live one
# --------------------------------------------------------------------------

@unittest.skipUnless(os.environ.get("COSHH_LIVE"),
                     "live smoke test: set COSHH_LIVE=1 (costs an API call and hits PubChem)")
class LiveSmokeTest(unittest.TestCase):
    """One real procedure, through the real model and the real PubChem."""

    PROCEDURE = (
        "To a stirred solution of toluene (2.12 g, 23 mmol) in dichloromethane (30 mL) "
        "at 0 C was added concentrated nitric acid (1.5 mL) dropwise over 10 minutes. "
        "The mixture was stirred for 1 h, then washed with water (2 x 25 mL). "
        "The original 1890 preparation used benzene, which is not used here."
    )

    def test_a_real_procedure_comes_back_assessed(self):
        out = manual.assess(self.PROCEDURE, title="Nitration", name="", date="",
                            college="", year="2")
        names = [row["name"].lower() for row in out["substances"]]
        self.assertTrue(any("toluene" in n for n in names), names)
        self.assertTrue(any("dichloromethane" in n or "dcm" in n for n in names), names)
        self.assertTrue(any("benzene" in s["name"].lower()
                            for s in out["mentioned_not_used"]), out["mentioned_not_used"])
        self.assertIn(HALOGENATED, out["waste"])
        self.assertTrue(out["review"])
        print(manual.as_text(out))


if __name__ == "__main__":
    unittest.main()
