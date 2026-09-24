"""
The hazard-code rules, checked code by code.

These are the tests that matter most in the repo: they are the record of what
the tool will tick on a form somebody signs. Everything here is offline — the
rules module holds no network code — so a rule can be argued with and re-run in
a second.

Each `test_h…` names one representative code per GHS hazard class and asserts
the route and the control the class exists to produce. The rest check the
behaviour that keeps the form honest: unknown codes, combined codes,
subdivision letters, and a substance PubChem knows nothing about.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coshh import rules  # noqa: E402
from coshh.rules import (  # noqa: E402
    ADD_DROPWISE, AQUEOUS, CONTROL_MEASURES, EXPOSURE_ROUTES, EYES, FIRE,
    FUMEHOOD, GAS, GLOVES, HALOGENATED, HYDROCARBON, INGESTION, INHALATION,
    LAB_COAT, MALODOROUS, NAMED_WASTE, NO_AIR, NO_FLAMES, NOT_IF_PREGNANT,
    NOT_NEAR_WATER, RUNAWAY, SILICA_TLC, SKIN, SPECIAL, SPECTACLES, SPILL,
    WATER_BATH,
)


def _pubchem(name, *codes, cas="", found=True):
    """The shape `safety.hazards()` returns, trimmed to what the rules read."""
    return {
        "found": found,
        "name": name,
        "cas": cas,
        "url": "https://pubchem.ncbi.nlm.nih.gov/compound/1",
        "primary": {
            "source": "Regulation (EC) No 1272/2008",
            "signal_word": "Danger",
            "pictograms": [],
            "hazards": [{"code": c, "text": rules.RULES[c].wording if c in rules.RULES else ""}
                        for c in codes],
            "precautions": [],
        },
        "other_sources": [],
        "note": None,
    }


def routes(*codes):
    return set(rules.exposure_routes(codes))


def controls(*codes):
    return set(rules.control_measures(codes))


class ExposureRouteTest(unittest.TestCase):
    """One code per class: does the route match the statement's own wording?"""

    def test_h314_corrosive_is_eyes_and_skin(self):
        # "Causes severe skin burns and eye damage" names both.
        self.assertEqual(routes("H314"), {EYES, SKIN})

    def test_h318_eye_damage_is_eyes_only(self):
        self.assertEqual(routes("H318"), {EYES})

    def test_h315_skin_irritation_is_skin_only(self):
        self.assertEqual(routes("H315"), {SKIN})

    def test_h330_fatal_if_inhaled_is_inhalation(self):
        self.assertEqual(routes("H330"), {INHALATION})

    def test_h335_and_h336_are_inhalation(self):
        self.assertEqual(routes("H335"), {INHALATION})
        self.assertEqual(routes("H336"), {INHALATION})

    def test_h301_toxic_if_swallowed_is_ingestion(self):
        self.assertEqual(routes("H301"), {INGESTION})

    def test_h311_toxic_in_contact_with_skin_is_skin(self):
        self.assertEqual(routes("H311"), {SKIN})

    def test_h304_aspiration_is_ingestion_and_inhalation(self):
        # The harm needs both steps the statement names: swallowed, then into the airways.
        self.assertEqual(routes("H304"), {INGESTION, INHALATION})

    def test_h350_carcinogen_covers_every_route(self):
        # Cumulative dose by any route, so no route is left off.
        self.assertEqual(routes("H350"), {SKIN, INHALATION, INGESTION})

    def test_h360_reproductive_covers_every_route(self):
        self.assertEqual(routes("H360"), {SKIN, INHALATION, INGESTION})

    def test_h225_flammable_liquid_includes_inhalation(self):
        # "liquid AND vapour": there is vapour above it at room temperature.
        self.assertIn(INHALATION, routes("H225"))

    def test_h290_corrosive_to_metals_ticks_no_route(self):
        # It is a statement about the apparatus, not about a person.
        self.assertEqual(routes("H290"), set())

    def test_h400_environmental_ticks_no_route(self):
        self.assertEqual(routes("H400"), set())

    def test_routes_are_returned_in_the_template_order(self):
        keys = list(rules.exposure_routes(["H302", "H330", "H314"]))
        self.assertEqual(keys, [r for r in EXPOSURE_ROUTES if r in keys])


class ControlMeasureTest(unittest.TestCase):

    def test_the_three_standing_controls_are_always_ticked(self):
        for option in (SPILL, SPECTACLES, LAB_COAT):
            self.assertIn(option, controls())
            self.assertIn(option, controls("H302"))

    def test_always_on_can_be_switched_off_for_inspection(self):
        self.assertEqual(set(rules.control_measures(["H302"], always_on=False)), {GLOVES})

    def test_h226_flammable_keeps_away_from_flames(self):
        self.assertIn(NO_FLAMES, controls("H226"))

    def test_h228_flammable_solid_keeps_away_from_flames(self):
        self.assertIn(NO_FLAMES, controls("H228"))

    def test_h314_corrosive_needs_gloves(self):
        self.assertIn(GLOVES, controls("H314"))

    def test_h331_toxic_if_inhaled_needs_the_fumehood(self):
        self.assertIn(FUMEHOOD, controls("H331"))

    def test_h260_water_reactive_stays_away_from_water(self):
        got = controls("H260")
        self.assertIn(NOT_NEAR_WATER, got)
        self.assertIn(ADD_DROPWISE, got)     # the quench is the dangerous step
        self.assertIn(NO_FLAMES, got)        # the gas released burns

    def test_h250_pyrophoric_is_kept_from_air(self):
        self.assertIn(NO_AIR, controls("H250"))

    def test_h361_reproductive_ticks_the_pregnancy_box(self):
        self.assertIn(NOT_IF_PREGNANT, controls("H361"))

    def test_h351_suspected_carcinogen_also_ticks_the_pregnancy_box(self):
        # Deliberately more cautious than autocoshh: this teaching lab restricts
        # the whole CMR set, not only the reproductive toxins.
        self.assertIn(NOT_IF_PREGNANT, controls("H351"))

    def test_h224_flammable_liquid_is_heated_on_a_bath(self):
        self.assertIn(WATER_BATH, controls("H224"))

    def test_h242_heating_may_cause_fire_is_heated_on_a_bath(self):
        self.assertIn(WATER_BATH, controls("H242"))

    def test_h230_does_not_claim_air_exclusion_helps(self):
        # "May react explosively even in the absence of air" — excluding air is not
        # the control, and ticking it would mislead the person reading the form.
        self.assertNotIn(NO_AIR, controls("H230"))

    def test_every_control_ticked_is_one_of_the_templates_eleven(self):
        for code in rules.RULES:
            for option in rules.control_measures([code]):
                self.assertIn(option, CONTROL_MEASURES)


class EuhStatementTest(unittest.TestCase):

    def test_euh029_liberates_toxic_gas_with_water(self):
        got = controls("EUH029")
        self.assertIn(NOT_NEAR_WATER, got)
        self.assertIn(FUMEHOOD, got)
        self.assertEqual(routes("EUH029") & {INHALATION}, {INHALATION})

    def test_euh019_peroxide_former_is_a_fire_question(self):
        sub = rules.assess_substance(_pubchem("diethyl ether", "EUH019"))
        self.assertTrue(rules.specific_risks([sub])[FIRE].ticked)


class CodeHandlingTest(unittest.TestCase):

    def test_codes_are_normalised(self):
        self.assertEqual(rules.normalise_code(" h315: "), "H315")
        self.assertEqual(rules.normalise_code("EUH 014"), "EUH014")
        self.assertEqual(rules.normalise_code("not a code"), "")

    def test_combined_codes_are_split_into_their_parts(self):
        self.assertEqual(rules.expand_codes(["H302 + H332"]), ("H302", "H332"))
        self.assertEqual(routes("H302 + H332"), {INGESTION, INHALATION})

    def test_subdivision_letters_fall_back_to_the_parent_code(self):
        # H361d, H350i and H360FD are the parent hazard with the endpoint spelled out.
        self.assertIs(rules.lookup("H361d"), rules.RULES["H361"])
        self.assertIs(rules.lookup("H350i"), rules.RULES["H350"])
        self.assertIn(NOT_IF_PREGNANT, controls("H360FD"))

    def test_duplicate_codes_collapse(self):
        self.assertEqual(rules.expand_codes(["H315", "h315", "H315:"]), ("H315",))

    def test_an_unknown_health_code_is_treated_cautiously_not_ignored(self):
        got_routes, got_controls = routes("H399"), controls("H399")
        self.assertEqual(got_routes, {SKIN, INHALATION, INGESTION})
        self.assertIn(GLOVES, got_controls)
        self.assertIn(FUMEHOOD, got_controls)

    def test_an_unknown_physical_code_still_answers_the_fire_question(self):
        sub = rules.assess_substance(_pubchem("mystery reagent", "H299"))
        self.assertIn("H299", sub.unknown_codes)
        self.assertTrue(rules.specific_risks([sub])[FIRE].ticked)

    def test_an_unknown_code_puts_the_substance_on_the_review_list(self):
        sub = rules.assess_substance(_pubchem("mystery reagent", "H299"))
        self.assertTrue(sub.needs_review)
        self.assertTrue(any("H299" in line for line in sub.review))

    def test_every_tick_carries_a_reason(self):
        sub = rules.assess_substance(_pubchem("sodium borohydride", "H260", "H301", "H314", "H360"))
        for tick in list(sub.exposure.values()) + list(sub.controls.values()):
            self.assertTrue(tick.why.strip(), f"{tick.option} was ticked with no reason")


class NoClassificationTest(unittest.TestCase):
    """The case the form must never make look clean."""

    def test_a_substance_with_no_classification_says_so_loudly(self):
        sub = rules.assess_substance({"found": False, "name": "novel ligand", "primary": None})
        self.assertFalse(sub.classified)
        self.assertIn("NO CLASSIFICATION FOUND", sub.hazards_text)
        self.assertTrue(sub.needs_review)

    def test_it_gets_barrier_and_containment_on_top_of_the_standing_controls(self):
        """An unassessed row must not be tick-for-tick identical to a blank one."""
        sub = rules.assess_substance({"found": False, "name": "novel ligand", "primary": None})
        self.assertEqual(set(sub.controls),
                         {SPILL, SPECTACLES, LAB_COAT, GLOVES, FUMEHOOD})
        self.assertIn("no GHS classification", sub.controls[GLOVES].why)

    def test_it_assumes_every_route_rather_than_asserting_none(self):
        """No route ticked reads as 'considered, and there is no way in'."""
        sub = rules.assess_substance({"found": False, "name": "novel ligand", "primary": None})
        self.assertEqual(list(sub.exposure), list(rules.EXPOSURE_ROUTES))

    def test_a_name_that_resolved_to_nothing_is_not_a_compound_nobody_classified(self):
        """One sends you to the SDS; the other sends you to the CAS number."""
        sub = rules.assess_substance(
            {"found": False, "cid": None, "name": "compound 7b", "primary": None})
        self.assertIn("NAME NOT RESOLVED", sub.hazards_text)
        self.assertIn("not the same as", " ".join(sub.review))
        resolved = rules.assess_substance(
            {"found": False, "cid": 516892, "name": "sodium bicarbonate", "primary": None})
        self.assertIn("NO CLASSIFICATION FOUND", resolved.hazards_text)

    def test_a_lookup_that_never_answered_is_not_a_lookup_that_found_nothing(self):
        sub = rules.assess_substance(
            {"found": False, "unreachable": True, "name": "toluene", "primary": None})
        self.assertFalse(sub.classified)
        self.assertIn("NOT CHECKED", sub.hazards_text)
        self.assertIn("never checked", " ".join(sub.review))
        self.assertEqual(list(sub.exposure), list(rules.EXPOSURE_ROUTES))

    def test_a_substance_never_looked_up_still_gets_a_row(self):
        form = rules.assess_form([], names=["novel ligand"])
        self.assertEqual(len(form.substances), 1)
        self.assertTrue(form.needs_review)


class SpecificRiskTest(unittest.TestCase):

    def test_a_flammable_answers_the_fire_question_yes_with_a_measure(self):
        sub = rules.assess_substance(_pubchem("diethyl ether", "H224"))
        row = rules.specific_risks([sub])[FIRE]
        self.assertTrue(row.ticked)
        self.assertTrue(row.prevention.strip())

    def test_a_pyrophoric_is_both_fire_and_thermal_runaway(self):
        sub = rules.assess_substance(_pubchem("tert-butyllithium", "H250"))
        got = rules.specific_risks([sub])
        self.assertTrue(got[FIRE].ticked)
        self.assertTrue(got[RUNAWAY].ticked)

    def test_a_water_reactive_answers_the_gas_question(self):
        sub = rules.assess_substance(_pubchem("sodium hydride", "H260"))
        self.assertTrue(rules.specific_risks([sub])[GAS].ticked)

    def test_an_unremarkable_substance_answers_every_question_no(self):
        sub = rules.assess_substance(_pubchem("sodium chloride", "H319"))
        got = rules.specific_risks([sub])
        self.assertEqual([row for row, r in got.items() if r.ticked], [])
        # …but the "no" is explained rather than left blank.
        self.assertTrue(got[FIRE].why.strip())

    def test_the_method_can_raise_thermal_runaway_on_its_own(self):
        got = rules.specific_risks([], procedure="The flask was cooled to 0 °C and the acid added dropwise.")
        self.assertTrue(got[RUNAWAY].ticked)

    def test_a_thiol_in_the_name_answers_the_smell_question(self):
        sub = rules.assess_substance(_pubchem("benzyl mercaptan", "H315"))
        row = rules.specific_risks([sub])[MALODOROUS]
        self.assertTrue(row.ticked)
        self.assertIn("bleach", row.prevention)

    def test_special_measures_is_left_for_the_chemist(self):
        row = rules.specific_risks([], procedure="anything")[SPECIAL]
        self.assertFalse(row.ticked)
        self.assertEqual(row.prevention, "")


class WasteTest(unittest.TestCase):

    def _ticks(self, *names, procedure=""):
        subs = [rules.assess_substance(None, name=n) for n in names]
        ticks, _review = rules.waste_streams(subs, procedure=procedure)
        return set(ticks)

    def test_dichloromethane_is_halogenated(self):
        self.assertIn(HALOGENATED, self._ticks("dichloromethane"))

    def test_toluene_is_hydrocarbon(self):
        self.assertIn(HYDROCARBON, self._ticks("toluene"))

    def test_dilute_hydrochloric_acid_is_aqueous(self):
        self.assertIn(AQUEOUS, self._ticks("hydrochloric acid"))

    def test_a_palladium_catalyst_is_named_waste(self):
        self.assertIn(NAMED_WASTE, self._ticks("palladium on carbon"))

    def test_a_column_fills_the_silica_bottle(self):
        got = self._ticks("ethyl acetate", procedure="Purified by column chromatography on silica gel.")
        self.assertIn(SILICA_TLC, got)

    def test_a_formula_overrules_an_unhelpful_name(self):
        subs = [rules.assess_substance(None, name="Compound 4b")]
        ticks, _ = rules.waste_streams(subs, formulae={"Compound 4b": "C12H14ClNO2"})
        self.assertIn(HALOGENATED, ticks)

    def test_an_unrecognised_substance_goes_to_named_waste_and_to_review(self):
        subs = [rules.assess_substance(None, name="Compound 4b")]
        ticks, review = rules.waste_streams(subs)
        self.assertIn(NAMED_WASTE, ticks)
        self.assertTrue(any("Compound 4b" in line for line in review))

    def test_aquatic_toxicity_keeps_it_out_of_the_sink(self):
        sub = rules.assess_substance(_pubchem("copper sulfate", "H410"))
        ticks, _ = rules.waste_streams([sub])
        self.assertIn(NAMED_WASTE, ticks)
        self.assertIn("sink", ticks[NAMED_WASTE].why)


class WholeFormTest(unittest.TestCase):

    def test_the_signature_is_never_filled_in(self):
        form = rules.assess_form([_pubchem("acetone", "H225", "H319", "H336")])
        self.assertTrue(any("Approved By" in line for line in form.review))

    def test_every_risk_row_is_answered_one_way_or_the_other(self):
        form = rules.assess_form([_pubchem("acetone", "H225")])
        self.assertEqual(set(form.risks), set(rules.RISK_ROWS))

    def test_a_row_is_never_silently_dropped(self):
        form = rules.assess_form([_pubchem("acetone", "H225")], names=["acetone", "novel ligand"])
        self.assertEqual([s.name for s in form.substances], ["acetone", "novel ligand"])


class TableIntegrityTest(unittest.TestCase):
    """Cheap checks that stop the table rotting."""

    def test_no_code_is_defined_twice(self):
        seen = []
        for klass in rules._CLASSES:
            seen.extend(klass.codes)
        self.assertEqual(len(seen), len(set(seen)))

    def test_every_rule_names_a_real_route_and_a_real_control(self):
        for code, rule in rules.RULES.items():
            for route in rule.routes:
                self.assertIn(route, EXPOSURE_ROUTES, code)
            for option in rule.controls:
                self.assertIn(option, CONTROL_MEASURES, code)
            for row in rule.risks:
                self.assertIn(row, rules.RISK_ROWS, code)

    def test_every_rule_that_ticks_something_explains_why(self):
        for code, rule in rules.RULES.items():
            if rule.routes:
                self.assertTrue(rule.route_why.strip(), code)
            if rule.controls:
                self.assertTrue(rule.control_why.strip(), code)
            if rule.risks:
                self.assertTrue(rule.risk_why.strip(), code)

    def test_the_reason_quotes_the_codes_own_wording(self):
        rule = rules.RULES["H314"]
        self.assertIn("Causes severe skin burns and eye damage", rule.route_why)


if __name__ == "__main__":
    unittest.main()
