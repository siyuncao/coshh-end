"""
The PubChem hazard lookup, parsed offline.

The fixture is the shape PubChem returns, trimmed: two sources that disagree,
a percentage on one of the H numbers, P numbers as links, and an icon URL the
pictogram code has to be read out of. Nothing here calls the network, so the
suite stays fast and does not depend on PubChem being up.
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import safety  # noqa: E402


def _info(ref, name, strings=(), markup=()):
    return {
        "ReferenceNumber": ref,
        "Name": name,
        "Value": {"StringWithMarkup": [{"String": s, "Markup": list(markup)} for s in strings]
                  or [{"String": "", "Markup": list(markup)}]},
    }


RECORD = {"Record": {
    "Reference": [
        {"ReferenceNumber": 47, "SourceName": "Regulation (EC) No 1272/2008 of the European Parliament"},
        {"ReferenceNumber": 22, "SourceName": "European Chemicals Agency (ECHA)"},
    ],
    "Section": [{"Section": [{"Section": [{
        "TOCHeading": "GHS Classification",
        "Information": [
            _info(47, "Pictogram(s)", markup=[
                {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS03.svg", "Extra": "Oxidizer"},
                {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS07.svg", "Extra": "Irritant"}]),
            _info(47, "Signal", ["Danger"]),
            _info(47, "GHS Hazard Statements",
                  ["H272: May intensify fire; oxidizer [Danger Oxidizing solids]",
                   "H302: Harmful if swallowed [Warning Acute toxicity, oral]"]),
            _info(47, "Precautionary Statement Codes", ["P210, P280, and P301+P317"], markup=[
                {"URL": "https://www.ncbi.nlm.nih.gov/ghs/#P210"},
                {"URL": "https://www.ncbi.nlm.nih.gov/ghs/#P280"},
                {"URL": "https://www.ncbi.nlm.nih.gov/ghs/#P301+P317"}]),
            _info(22, "Signal", ["Danger"]),
            _info(22, "GHS Hazard Statements",
                  ["H314 (91.7%): Causes severe skin burns [Danger Skin corrosion]"]),
            _info(22, "Note", ["This chemical does not meet GHS hazard criteria for 7.8% of reports."]),
        ],
    }]}]}],
}}


class ParsingTest(unittest.TestCase):

    def setUp(self):
        safety._cache.clear()
        self.addCleanup(safety._cache.clear)

    def classify(self):
        with mock.patch.object(safety, "_get", lambda *a, **k: RECORD):
            return safety.classify(516875)

    def test_the_harmonised_block_is_read_whole(self):
        first = self.classify()["classifications"][0]
        self.assertEqual(first["signal_word"], "Danger")
        self.assertEqual([p["code"] for p in first["pictograms"]], ["GHS03", "GHS07"])
        self.assertEqual([p["meaning"] for p in first["pictograms"]], ["Oxidizer", "Irritant"])
        self.assertEqual([h["code"] for h in first["hazards"]], ["H272", "H302"])
        self.assertEqual(first["hazards"][0]["text"], "May intensify fire; oxidizer")
        self.assertEqual(first["hazards"][0]["classification"], "Danger Oxidizing solids")
        self.assertEqual(first["precautions"], ["P210", "P280", "P301+P317"])

    def test_sources_are_kept_apart_and_named(self):
        blocks = self.classify()["classifications"]
        self.assertEqual(len(blocks), 2)
        self.assertIn("1272/2008", blocks[0]["source"])
        self.assertIn("ECHA", blocks[1]["source"])

    def test_a_percentage_is_agreement_not_part_of_the_statement(self):
        second = self.classify()["classifications"][1]
        self.assertEqual(second["hazards"][0]["code"], "H314")
        self.assertEqual(second["hazards"][0]["agreement"], 91.7)
        self.assertNotIn("%", second["hazards"][0]["text"])

    def test_the_harmonised_source_is_the_one_quoted(self):
        with mock.patch.object(safety, "find_cid", lambda *a, **k: 516875), \
             mock.patch.object(safety, "_get", lambda *a, **k: RECORD):
            answer = safety.hazards("potassium permanganate", "7722-64-7")
        self.assertTrue(answer["found"])
        self.assertIn("1272/2008", answer["primary"]["source"])
        self.assertEqual(len(answer["other_sources"]), 1)

    def test_nothing_known_says_so_instead_of_looking_safe(self):
        with mock.patch.object(safety, "_get", lambda *a, **k: None):
            answer = safety.hazards("zz-test-unknown-compound")
        self.assertFalse(answer["found"])
        self.assertIsNone(answer["primary"])
        self.assertIn("safety data sheet", answer["note"])

    def test_the_answer_is_cached_so_one_compound_is_one_lookup(self):
        calls = []

        def counted(path, **params):
            calls.append(path)
            if "pug_view" in path:
                return RECORD
            if "property/Title" in path:
                return {"PropertyTable": {"Properties": [
                    {"CID": 516875, "Title": "Potassium Permanganate"}]}}
            return {"IdentifierList": {"CID": [516875]}}

        with mock.patch.object(safety, "_get", counted):
            safety.hazards("potassium permanganate", "7722-64-7")
            safety.hazards("Potassium Permanganate ", "7722-64-7")
        # one id lookup, one title, one classification — then the cache answers
        self.assertEqual(len(calls), 3)

    def test_the_title_pubchem_resolved_to_is_carried_back(self):
        """PubChem maps a near-miss onto a different compound; the title shows it."""
        def answering(path, **params):
            if "property/Title" in path:
                return {"PropertyTable": {"Properties": [{"CID": 174, "Title": "Ethylene Glycol"}]}}
            return {"IdentifierList": {"CID": [174]}}

        with mock.patch.object(safety, "_get", answering):
            answer = safety.hazards("PEG")
        self.assertEqual(answer["resolved_title"], "Ethylene Glycol")

    def test_a_pubchem_outage_is_not_reported_as_an_absence_of_data(self):
        """'Nobody classified it' and 'nobody answered' are different sentences."""
        with mock.patch.object(safety.httpx, "get", mock.Mock(side_effect=OSError("down"))):
            answer = safety.hazards("pyrrolidine", "123-75-1")
        self.assertFalse(answer["found"])
        self.assertTrue(answer["unreachable"])
        self.assertIn("could not be reached", answer["note"])
        self.assertNotIn("holds no GHS", answer["note"])

    def test_an_outage_is_not_cached_so_the_next_lookup_tries_again(self):
        """A blink mid-draft must not freeze 'unclassified' for the whole session."""
        with mock.patch.object(safety.httpx, "get", mock.Mock(side_effect=OSError("down"))):
            first = safety.hazards("toluene")
        self.assertTrue(first["unreachable"])

        def answering(path, **params):
            if "pug_view" in path:
                return RECORD
            if "property/Title" in path:
                return {"PropertyTable": {"Properties": [{"CID": 1140, "Title": "Toluene"}]}}
            return {"IdentifierList": {"CID": [1140]}}

        with mock.patch.object(safety, "_get", answering):
            second = safety.hazards("toluene")
        self.assertTrue(second["found"])
        self.assertFalse(second["unreachable"])

    def test_a_server_error_is_an_outage_but_a_404_is_an_answer(self):
        class Reply:
            def __init__(self, code):
                self.status_code = code

            def json(self):
                return {}

        with mock.patch.object(safety.httpx, "get", lambda *a, **k: Reply(503)):
            with self.assertRaises(safety.PubChemUnreachable):
                safety._get("/whatever")
        with mock.patch.object(safety.httpx, "get", lambda *a, **k: Reply(404)):
            self.assertIsNone(safety._get("/whatever"))


if __name__ == "__main__":
    unittest.main()
