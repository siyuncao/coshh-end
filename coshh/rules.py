"""
From GHS hazard codes to the ticks this COSHH form asks for.

The form (Oxford, *COSHH Form, Chemistry Teaching Laboratory*) does not ask for
prose. It asks, per substance, which of four **exposure routes** apply and which
of eleven **control measures** are in use, then asks the whole experiment four
yes/no questions about **specific risks** and which **waste streams** it fills.
Those are the only answers it will accept, so this module's whole job is to turn
a list of H numbers into exactly those answers.

Three commitments, because a person signs this form:

1. **Every tick carries a reason.** A `Tick` holds the code that caused it, that
   code's own published wording, and a sentence saying why the wording implies
   the tick. If a demonstrator asks "why is the fume hood ticked", the answer is
   in the object, not in somebody's memory.
2. **Conservative when unsure.** An unrecognised code, or a substance PubChem
   has no classification for, never comes out looking clean. It ticks the
   protective options its family implies and adds a loud line to `review`.
3. **Judgement stays with the chemist.** Scale, containment, quench plan and the
   "Approved By" signature are not derivable from an H number, so this module
   does not derive them. It says what it cannot know.

The mapping is a table, not a pile of `if`s, so that it can be read straight
through and argued with. The table is grouped by GHS hazard class, because the
classes are what the codes mean; the reason strings are written from the code's
own published wording rather than from a habit about the substance.

Credit: the option lists and the shape of the code -> exposure/control mapping
were checked against `aymannel/autocoshh` (MIT), which fills the same Oxford
form. Where this module is deliberately more cautious than that one, the
divergence is marked `DIVERGENCE` in the comments and listed in docs/rules.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# The form's vocabulary.
#
# These strings are the template's own labels, read out of the .docx (see
# docs/template-anatomy.md). The writer matches on them, so they are exact and
# must not be "tidied": leading spaces are stripped at match time, not here.
# --------------------------------------------------------------------------

EYES = "Eyes"
SKIN = "Skin"
INHALATION = "Inhalation"
INGESTION = "Ingestion"
EXPOSURE_ROUTES: Tuple[str, ...] = (EYES, SKIN, INHALATION, INGESTION)

SPILL = "In case of spill, consult a demonstrator, technician or senior member of staff"
SPECTACLES = "Safety spectacles"
LAB_COAT = "Lab coat"
GLOVES = "Gloves"
FUMEHOOD = "Fumehood"
NO_FLAMES = "Keep away from naked flames and sources of ignition"
WATER_BATH = "Heat using temperature-controlled water bath"
NOT_IF_PREGNANT = "Not to be used if pregnant"
NOT_NEAR_WATER = "Do not store or use near water (store in oil)"
ADD_DROPWISE = "Add dropwise to solution"
NO_AIR = "Do not expose to air"
CONTROL_MEASURES: Tuple[str, ...] = (
    SPILL, SPECTACLES, LAB_COAT, GLOVES, FUMEHOOD, NO_FLAMES,
    WATER_BATH, NOT_IF_PREGNANT, NOT_NEAR_WATER, ADD_DROPWISE, NO_AIR,
)

# The three the department ticks on every row of a blank form. The template
# itself ships rows 2-5 pre-ticked with exactly these, so keeping them is
# matching the paper form, not adding to it.
ALWAYS_ON: Tuple[str, ...] = (SPILL, SPECTACLES, LAB_COAT)
ALWAYS_ON_WHY = (
    "ticked on every row of the blank template: this teaching lab requires eye "
    "protection and a lab coat at all times, and the spill line is the standing "
    "instruction, not a substance-specific judgement"
)

FIRE = "Fire or Explosion"
RUNAWAY = "Thermal Runaway"
GAS = "Gas Release"
MALODOROUS = "Malodorous Substances"
SPECIAL = "Special measures:"
RISK_ROWS: Tuple[str, ...] = (FIRE, RUNAWAY, GAS, MALODOROUS, SPECIAL)

HALOGENATED = "Halogenated"
AQUEOUS = "Aqueous"
HYDROCARBON = "Hydrocarbon"
NAMED_WASTE = "Named Waste"
CONTAMINATED_SOLID = "Contaminated solid waste"
SILICA_TLC = "Silica/TLC"
WASTE_STREAMS: Tuple[str, ...] = (
    HALOGENATED, AQUEOUS, HYDROCARBON, NAMED_WASTE, CONTAMINATED_SOLID, SILICA_TLC,
)


# --------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Tick:
    """One box, and the argument for ticking it."""

    option: str           # the template's own label
    why: str              # one sentence a demonstrator can check
    codes: Tuple[str, ...] = ()   # the H numbers that drove it ("" for standing rules)

    def __str__(self) -> str:
        return f"{self.option} — {self.why}"


@dataclass(frozen=True)
class RiskRow:
    """A row of the Specific Safety or Risk Implication table."""

    row: str
    ticked: bool
    prevention: str = ""          # goes in the "If Yes, Prevention Measures" cell
    why: str = ""
    codes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Rule:
    """What one hazard code implies, and why."""

    code: str
    wording: str                  # the code's own published statement
    hazard_class: str
    routes: Tuple[str, ...] = ()
    route_why: str = ""
    controls: Tuple[str, ...] = ()
    control_why: str = ""
    risks: Tuple[str, ...] = ()
    risk_why: str = ""
    prevention: str = ""          # suggested text for the prevention-measures cell
    review: str = ""              # a line for the "check this" list, when the code needs one


@dataclass
class SubstanceAssessment:
    """One row of the substance table, with its reasoning attached."""

    name: str
    cas: str = ""
    amount: str = ""
    classified: bool = True
    hazards_text: str = ""                              # column 3 of the form
    codes: Tuple[str, ...] = ()                         # codes as published
    unknown_codes: Tuple[str, ...] = ()                 # codes with no rule
    exposure: Dict[str, Tick] = field(default_factory=dict)
    controls: Dict[str, Tick] = field(default_factory=dict)
    risks: Tuple[RiskRow, ...] = ()                     # risk rows this substance argues for
    review: Tuple[str, ...] = ()                        # loud "a human must check this"
    source: str = ""                                    # who classified it
    url: str = ""

    @property
    def needs_review(self) -> bool:
        return bool(self.review) or not self.classified


@dataclass
class FormAssessment:
    """The whole form: rows, the four risk questions, waste, and what to check."""

    substances: Tuple[SubstanceAssessment, ...] = ()
    risks: Dict[str, RiskRow] = field(default_factory=dict)
    waste: Dict[str, Tick] = field(default_factory=dict)
    review: Tuple[str, ...] = ()

    @property
    def needs_review(self) -> bool:
        return bool(self.review) or any(s.needs_review for s in self.substances)


# --------------------------------------------------------------------------
# The table.
#
# One entry per GHS hazard class. `codes` maps each code to its own published
# wording, so the reason string can quote the code rather than paraphrase it.
# Reading order is the GHS order: physical hazards, then health, then
# environment, then the EU-only EUH statements.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class _Class:
    name: str
    codes: Dict[str, str]
    routes: Tuple[str, ...] = ()
    route_why: str = ""
    controls: Tuple[str, ...] = ()
    control_why: str = ""
    risks: Tuple[str, ...] = ()
    risk_why: str = ""
    prevention: str = ""
    review: str = ""


_CLASSES: Tuple[_Class, ...] = (

    # --- Physical: explosives -------------------------------------------
    _Class(
        name="Explosives",
        codes={
            "H200": "Unstable explosive",
            "H201": "Explosive; mass explosion hazard",
            "H202": "Explosive; severe projection hazard",
            "H203": "Explosive; fire, blast or projection hazard",
            "H204": "Fire or projection hazard",
            "H205": "May mass explode in fire",
        },
        routes=(EYES, SKIN),
        route_why="an explosion injures by blast and by fragments, which reach the eyes and any unprotected skin first",
        controls=(NO_FLAMES, WATER_BATH),
        control_why="an explosive must be kept away from every ignition source, and any heating must go through a "
                    "temperature-controlled bath rather than a flame or a hotplate where the temperature can run",
        risks=(FIRE, RUNAWAY),
        risk_why="the statement is itself a statement of explosion hazard",
        prevention="Smallest workable quantity behind a blast screen; no ignition sources; "
                   "temperature-controlled heating only.",
        review="Explosive classification — agree the scale, the screening and who is present with a demonstrator "
               "before any of this is weighed out.",
    ),

    # --- Physical: self-reactives and organic peroxides ------------------
    _Class(
        name="Self-reactive substances and organic peroxides",
        codes={
            "H240": "Heating may cause an explosion",
            "H241": "Heating may cause a fire or explosion",
            "H242": "Heating may cause a fire",
        },
        routes=(EYES, SKIN),
        route_why="the failure mode is a fire or an explosion at the bench, which reaches eyes and skin",
        controls=(NO_FLAMES, WATER_BATH),
        control_why="the code names heating as the trigger, so heating is the thing to control: a bath with a set "
                    "temperature, never an open flame",
        risks=(FIRE, RUNAWAY),
        risk_why="'heating may cause' is the definition of a runaway that ends in fire or explosion",
        prevention="Temperature-controlled bath with the set point recorded; no direct flame; do not exceed the "
                   "self-accelerating decomposition temperature on the SDS.",
        review="Self-reactive or peroxide — check the self-accelerating decomposition temperature on the SDS and "
               "keep the working temperature well below it.",
    ),
    _Class(
        name="Self-reactives that do not need air",
        codes={
            "H230": "May react explosively even in the absence of air",
            "H231": "May react explosively even in the absence of air at elevated pressure and/or temperature",
        },
        routes=(EYES, SKIN),
        route_why="an explosive decomposition injures by blast and fragments",
        controls=(NO_FLAMES, WATER_BATH),
        control_why="inerting does not help here — the code says so — so the controls left are ignition sources and "
                    "controlled heating",
        # DIVERGENCE from autocoshh, which ticks "Do not expose to air" for H230/H231. The code says the
        # substance reacts *without* air; excluding air is not the control, and ticking it would mislead.
        risks=(FIRE, RUNAWAY),
        risk_why="an explosive reaction that does not need air cannot be stopped by blanketing it",
        prevention="Keep below the pressure and temperature limits on the SDS; inert atmosphere is not a control here.",
        review="Reacts explosively without air — an inert blanket is not protection. Confirm the temperature and "
               "pressure limits with a demonstrator.",
    ),

    # --- Physical: flammables -------------------------------------------
    _Class(
        name="Flammable gases and aerosols",
        codes={
            "H220": "Extremely flammable gas",
            "H221": "Flammable gas",
            "H222": "Extremely flammable aerosol",
            "H223": "Flammable aerosol",
        },
        routes=(INHALATION,),
        route_why="it is released as a gas or a spray, so it is in the air you are standing in",
        controls=(NO_FLAMES, FUMEHOOD),
        control_why="a flammable gas needs every ignition source removed and needs extraction so it cannot build to "
                    "its lower explosive limit in the room",
        risks=(FIRE, GAS),
        risk_why="the substance is a gas and it burns",
        prevention="Fume hood with the sash low; no naked flames or hot surfaces; cylinder secured and the line "
                   "leak-checked before use.",
    ),
    _Class(
        name="Flammable liquids",
        codes={
            "H224": "Extremely flammable liquid and vapour",
            "H225": "Highly flammable liquid and vapour",
            "H226": "Flammable liquid and vapour",
            "H227": "Combustible liquid",
        },
        routes=(SKIN, INHALATION),
        # DIVERGENCE from autocoshh, which ticks skin only. A liquid flammable enough to be labelled
        # "liquid AND vapour" has a vapour above it at room temperature by definition, so inhalation is
        # a live route whether or not a separate H336 happens to be on the label.
        route_why="the statement says 'liquid and vapour': there is vapour above it at room temperature, so it is "
                  "breathed as well as touched",
        controls=(NO_FLAMES, WATER_BATH, FUMEHOOD),
        control_why="vapour travels to a distant ignition source, so flames go; if it must be heated it goes on a "
                    "water bath, not a hotplate; and the hood keeps the vapour out of the room",
        risks=(FIRE,),
        risk_why="the vapour, not the liquid, is what ignites, and it spreads",
        prevention="Fume hood; no naked flames in the bay; heat only on a temperature-controlled water bath; "
                   "keep the bottle closed when not pouring.",
    ),
    _Class(
        name="Flammable solids",
        codes={"H228": "Flammable solid"},
        routes=(SKIN,),
        route_why="it is handled as a solid, so contact is the route that exists at the bench",
        controls=(NO_FLAMES,),
        control_why="the hazard is ignition, so the control is removing ignition sources",
        risks=(FIRE,),
        risk_why="a flammable solid burns where it is spilled",
        prevention="No ignition sources; sweep up spills immediately; do not grind or generate dust.",
    ),

    # --- Physical: pyrophoric and self-heating ---------------------------
    _Class(
        name="Pyrophoric substances",
        codes={"H250": "Catches fire spontaneously if exposed to air"},
        routes=(SKIN,),
        route_why="it ignites on contact with air, so the injury is a burn where it touches",
        controls=(NO_AIR, NO_FLAMES, GLOVES),
        control_why="the code names air as the trigger, so air exclusion is the control; gloves because a syringe "
                    "or cannula transfer puts your hands next to the thing that lights on contact",
        risks=(FIRE, RUNAWAY),
        risk_why="spontaneous ignition is a fire with no ignition source to remove",
        prevention="Schlenk line or glovebox; septum and cannula or syringe transfer under inert gas; quench waste "
                   "and needles deliberately, never in the bin.",
        review="Pyrophoric — do not run this unsupervised. Agree the transfer and the quench with a demonstrator, "
               "and have dry sand to hand.",
    ),
    _Class(
        name="Self-heating substances",
        codes={
            "H251": "Self-heating; may catch fire",
            "H252": "Self-heating in large quantities; may catch fire",
        },
        routes=(SKIN,),
        route_why="the hazard is a burn from material that has heated itself where it sits",
        controls=(NO_AIR, NO_FLAMES),
        control_why="self-heating is oxidation by air, so keeping it sealed is the control, and ignition sources go "
                    "because the end point is a fire",
        risks=(FIRE, RUNAWAY),
        risk_why="self-heating is a runaway by definition: the reaction supplies its own heat",
        prevention="Keep the container closed and in small quantities; do not pile up used filter cake or wipes; "
                   "do not leave residues on the bench overnight.",
        review="Self-heating — the residue and the waste are as much of a fire risk as the bottle. Agree how the "
               "waste is quenched and stored.",
    ),

    # --- Physical: water-reactive ---------------------------------------
    _Class(
        name="Substances which in contact with water emit flammable gases",
        codes={
            "H260": "In contact with water releases flammable gases which may ignite spontaneously",
            "H261": "In contact with water releases flammable gas",
        },
        routes=(EYES, SKIN),
        route_why="water on the skin or in the eye is enough to set it off, and a violent evolution of gas sprays "
                  "what is in the flask",
        controls=(NOT_NEAR_WATER, NO_FLAMES, GLOVES, ADD_DROPWISE),
        control_why="the code names water as the trigger, so water goes; the gas released is flammable, so ignition "
                    "sources go; and any deliberate contact with water — the quench — is made dropwise so the gas "
                    "comes off at a rate the apparatus can vent",
        risks=(FIRE, GAS),
        risk_why="the statement is a statement of gas evolution, and the gas burns",
        prevention="Dry glassware and dry solvent; store under oil or inert gas; quench dropwise into a stirred "
                   "quench at 0 °C behind a screen, with no flames in the bay.",
        review="Water-reactive — write the quench down before you start, including what you quench into and at what "
               "temperature, and have a demonstrator check it.",
    ),

    # --- Physical: oxidisers and gases under pressure --------------------
    _Class(
        name="Oxidising substances",
        codes={
            "H270": "May cause or intensify fire; oxidizer",
            "H271": "May cause fire or explosion; strong oxidizer",
            "H272": "May intensify fire; oxidizer",
        },
        routes=(EYES, SKIN),
        route_why="strong oxidisers attack tissue on contact as well as feeding a fire",
        controls=(NO_FLAMES, GLOVES),
        control_why="an oxidiser turns anything combustible nearby into the fuel, so it is kept away from ignition "
                    "sources and from paper, solvent and glove boxes of tissue; gloves because contact damages skin",
        risks=(FIRE,),
        risk_why="the code's own words: it causes or intensifies fire",
        prevention="Keep away from organics, paper and solvent bottles; separate spatulas; no ignition sources; "
                   "never return unused solid to the stock bottle.",
        review="Oxidiser — check nothing combustible is stored with it, and that the spatula is clean.",
    ),
    _Class(
        name="Gases under pressure",
        codes={
            "H280": "Contains gas under pressure; may explode if heated",
            "H281": "Contains refrigerated gas; may cause cryogenic burns or injury",
        },
        routes=(EYES, SKIN),
        route_why="a burst cylinder or a cryogenic splash injures eyes and skin directly",
        controls=(GLOVES,),
        control_why="cryogenic and high-pressure transfers need the hands covered; the rest of the control is the "
                    "cylinder restraint, which this form has no box for",
        risks=(FIRE, GAS),
        risk_why="a pressurised container that fails releases its whole contents at once",
        prevention="Cylinder clamped and the valve capped when moving; regulator checked; never heat the cylinder; "
                   "cryogenic gloves and a face shield for transfers.",
        review="Gas under pressure — the cylinder restraint and regulator are not on this form. Note them under "
               "Special measures.",
    ),
    _Class(
        name="Corrosive to metals",
        codes={"H290": "May be corrosive to metals"},
        routes=(),
        # H290 is a statement about the apparatus, not about people. The route ticks stay off unless a
        # health code puts them on; what changes is the glassware and the clamps.
        route_why="",
        controls=(GLOVES,),
        control_why="this code is about the apparatus rather than the person, but anything corrosive enough to eat "
                    "a clamp is handled gloved",
        risks=(),
        risk_why="",
        review="Corrosive to metals — use glass or PTFE, keep it off the clamps and the balance, and do not leave "
               "it in a metal-capped bottle.",
    ),

    # --- Health: acute toxicity ------------------------------------------
    _Class(
        name="Acute toxicity, oral",
        codes={
            "H300": "Fatal if swallowed",
            "H301": "Toxic if swallowed",
            "H302": "Harmful if swallowed",
            "H303": "May be harmful if swallowed",
        },
        routes=(INGESTION,),
        route_why="the statement's own words are 'if swallowed'",
        controls=(GLOVES,),
        # DIVERGENCE from autocoshh, which ticks no glove for oral toxicity. In a lab nobody drinks the
        # reagent; it is swallowed off a contaminated hand, so the glove is the control that matches the route.
        control_why="nobody drinks it deliberately — it is swallowed off a contaminated hand or a contaminated pen, "
                    "so the glove is the control that actually interrupts the route",
        prevention="",
        review="",
    ),
    _Class(
        name="Acute toxicity, dermal",
        codes={
            "H310": "Fatal in contact with skin",
            "H311": "Toxic in contact with skin",
            "H312": "Harmful in contact with skin",
            "H313": "May be harmful in contact with skin",
        },
        routes=(SKIN,),
        route_why="the statement's own words are 'in contact with skin'",
        controls=(GLOVES,),
        control_why="the route is the skin, so the control is the barrier on the skin",
        review="Toxic by skin contact — check the glove material against the SDS breakthrough table; nitrile is not "
               "right for everything.",
    ),
    _Class(
        name="Acute toxicity, inhalation",
        codes={
            "H330": "Fatal if inhaled",
            "H331": "Toxic if inhaled",
            "H332": "Harmful if inhaled",
            "H333": "May be harmful if inhaled",
        },
        routes=(INHALATION,),
        route_why="the statement's own words are 'if inhaled'",
        controls=(FUMEHOOD,),
        control_why="the route is the air, so the control is keeping it out of the air you are in",
        review="",
    ),
    _Class(
        name="Aspiration hazard",
        codes={
            "H304": "May be fatal if swallowed and enters airways",
            "H305": "May be harmful if swallowed and enters airways",
        },
        routes=(INGESTION, INHALATION),
        route_why="the harm needs both steps the statement names: it is swallowed, then it enters the airways",
        controls=(FUMEHOOD,),
        control_why="the substances that carry this code are thin, volatile hydrocarbons, so the hood is already the "
                    "right place for them",
        review="Aspiration hazard — never pipette by mouth, and if it is swallowed do not induce vomiting; say so "
               "when you call for help.",
    ),

    # --- Health: corrosion, irritation, sensitisation ---------------------
    _Class(
        name="Skin corrosion / serious eye damage",
        codes={"H314": "Causes severe skin burns and eye damage"},
        routes=(EYES, SKIN),
        route_why="the statement names both: skin burns and eye damage",
        controls=(GLOVES,),
        control_why="a corrosive burns on contact, so the barrier goes on before the bottle is opened",
        review="Corrosive — know where the nearest eyewash and safety shower are before you start, and add "
               "corrosive to water, never water to corrosive.",
    ),
    _Class(
        name="Skin irritation",
        codes={
            "H315": "Causes skin irritation",
            "H316": "Causes mild skin irritation",
        },
        routes=(SKIN,),
        route_why="the statement names the skin",
        controls=(GLOVES,),
        control_why="the barrier is the control for a substance that damages skin on contact",
    ),
    _Class(
        name="Skin sensitisation",
        codes={"H317": "May cause an allergic skin reaction"},
        routes=(SKIN,),
        route_why="the statement names an allergic reaction of the skin",
        controls=(GLOVES,),
        control_why="sensitisation has no safe contact dose, so the aim is no contact at all",
        review="Skin sensitiser — one exposure can sensitise you for life. Change gloves the moment they are "
               "splashed rather than at the end.",
    ),
    _Class(
        name="Serious eye damage / eye irritation",
        codes={
            "H318": "Causes serious eye damage",
            "H319": "Causes serious eye irritation",
            "H320": "Causes eye irritation",
        },
        routes=(EYES,),
        route_why="the statement names the eye",
        controls=(GLOVES,),
        # DIVERGENCE from autocoshh, which ticks no glove for eye-only codes. The splash that reaches an
        # eye came off a hand or a pipette; the glove is cheap and the eye is not.
        control_why="what reaches an eye is a splash from a hand or a pipette, so the glove is part of keeping it "
                    "away from the face; the spectacles are already ticked as standard",
        review="",
    ),
    _Class(
        name="Respiratory sensitisation",
        codes={"H334": "May cause allergy or asthma symptoms or breathing difficulties if inhaled"},
        routes=(INHALATION,),
        route_why="the statement's own words are 'if inhaled'",
        controls=(FUMEHOOD,),
        control_why="a respiratory sensitiser has no safe airborne dose, so it stays in the hood at all times",
        review="Respiratory sensitiser — tell a demonstrator if you have asthma before handling this, and keep the "
               "sash as low as the work allows.",
    ),
    _Class(
        name="Specific target organ toxicity, single exposure (irritation / narcosis)",
        codes={
            "H335": "May cause respiratory irritation",
            "H336": "May cause drowsiness or dizziness",
        },
        routes=(INHALATION,),
        route_why="both effects are effects of breathing the vapour",
        controls=(FUMEHOOD,),
        control_why="the effect is caused by the vapour reaching you, so the hood is the control",
    ),

    # --- Health: CMR ------------------------------------------------------
    _Class(
        name="Germ cell mutagenicity",
        codes={
            "H340": "May cause genetic defects",
            "H341": "Suspected of causing genetic defects",
        },
        routes=(SKIN, INHALATION, INGESTION),
        route_why="a mutagenic effect is driven by dose, not by which door the dose came through, so every route "
                  "that exists at the bench is ticked",
        controls=(GLOVES, FUMEHOOD, NOT_IF_PREGNANT),
        control_why="the aim is no exposure by any route: barrier on the hands, containment for the vapour, and — "
                    "because a germ cell mutagen acts on the material passed to a child — the pregnancy restriction",
        review="Mutagen — use the smallest quantity that works, keep it in the hood, and ask whether a less "
               "hazardous substitute would do the same job.",
    ),
    _Class(
        name="Carcinogenicity",
        codes={
            "H350": "May cause cancer",
            "H351": "Suspected of causing cancer",
        },
        routes=(SKIN, INHALATION, INGESTION),
        route_why="a carcinogenic effect is driven by cumulative dose by any route, so every route that exists at "
                  "the bench is ticked",
        controls=(GLOVES, FUMEHOOD, NOT_IF_PREGNANT),
        # DIVERGENCE from autocoshh, which ticks the pregnancy restriction only for reproductive toxins.
        # Teaching labs restrict the whole CMR set for pregnant students; ticking it here is the cautious
        # reading and costs nothing but a conversation.
        control_why="no threshold is assumed for a carcinogen, so contact and vapour are both engineered out, and "
                    "the pregnancy restriction is ticked because this teaching lab restricts the whole CMR set",
        review="Carcinogen — named substance. Use the smallest quantity, keep it in the hood, and ask whether a "
               "substitute exists before ordering more.",
    ),
    _Class(
        name="Reproductive toxicity",
        codes={
            "H360": "May damage fertility or the unborn child",
            "H361": "Suspected of damaging fertility or the unborn child",
            "H362": "May cause harm to breast-fed children",
        },
        routes=(SKIN, INHALATION, INGESTION),
        route_why="the effect follows the dose that reaches the bloodstream, whichever route delivered it",
        controls=(GLOVES, FUMEHOOD, NOT_IF_PREGNANT),
        control_why="this is the code the 'Not to be used if pregnant' box exists for, and the glove and the hood "
                    "are what keep the dose at zero for everybody else",
        review="Reproductive toxin — if you are or may be pregnant or breast-feeding, speak to a demonstrator "
               "before this experiment rather than during it.",
    ),
    _Class(
        name="Specific target organ toxicity, organ damage",
        codes={
            "H370": "Causes damage to organs",
            "H371": "May cause damage to organs",
            "H372": "Causes damage to organs through prolonged or repeated exposure",
            "H373": "May cause damage to organs through prolonged or repeated exposure",
        },
        routes=(SKIN, INHALATION, INGESTION),
        route_why="organ damage follows the systemic dose, so every route that can deliver a dose is ticked",
        controls=(GLOVES, FUMEHOOD),
        control_why="keep the systemic dose at zero: barrier on the hands and containment for anything airborne",
        review="Organ toxicity — read which organ is named on the SDS; for a repeated-exposure code it is the "
               "number of times you handle it that matters, not one session.",
    ),

    # --- Environment ------------------------------------------------------
    _Class(
        name="Hazardous to the aquatic environment",
        codes={
            "H400": "Very toxic to aquatic life",
            "H401": "Toxic to aquatic life",
            "H402": "Harmful to aquatic life",
            "H410": "Very toxic to aquatic life with long-lasting effects",
            "H411": "Toxic to aquatic life with long-lasting effects",
            "H412": "Harmful to aquatic life with long-lasting effects",
            "H413": "May cause long-lasting harmful effects to aquatic life",
            "H420": "Harms public health and the environment by destroying ozone in the upper atmosphere",
        },
        routes=(),
        route_why="",
        controls=(),
        control_why="",
        review="Hazardous to the environment — nothing containing this goes down the sink, including the rinsings. "
               "Collect it as named waste.",
    ),

    # --- EU-only supplemental statements ----------------------------------
    # PubChem returns these alongside the H numbers for EU-classified substances,
    # and several of them are the only warning a form would otherwise get about
    # gas evolution, so they are treated as first-class rules.
    _Class(
        name="Supplemental EU statements: reaction with water",
        codes={
            "EUH014": "Reacts violently with water",
            "EUH029": "Contact with water liberates toxic gas",
        },
        routes=(EYES, SKIN, INHALATION),
        route_why="a violent reaction sprays the contents at the face, and the gas released is breathed",
        controls=(NOT_NEAR_WATER, FUMEHOOD, GLOVES, ADD_DROPWISE),
        control_why="water is the named trigger, the product is a gas that must stay in the hood, and any "
                    "deliberate contact with water is made dropwise so the rate stays controllable",
        risks=(GAS,),
        risk_why="the statement is a statement about releasing gas",
        prevention="Dry glassware; quench dropwise into a stirred, cooled quench inside the hood with the sash low.",
        review="Reacts with water — write the quench down before you start and have it checked.",
    ),
    _Class(
        name="Supplemental EU statements: reaction with acid",
        codes={
            "EUH031": "Contact with acids liberates toxic gas",
            "EUH032": "Contact with acids liberates very toxic gas",
        },
        routes=(INHALATION,),
        route_why="the harm is the gas, and the gas is breathed",
        controls=(FUMEHOOD,),
        control_why="the gas has to be contained, and the hood is the only containment this form offers",
        risks=(GAS,),
        risk_why="the statement is a statement about releasing gas",
        prevention="Keep acids out of this waste stream and out of the same spill tray; work in the hood.",
        review="Liberates toxic gas with acid — check nothing acidic shares the waste container or the spill tray.",
    ),
    _Class(
        name="Supplemental EU statements: peroxide formation and confinement",
        codes={
            "EUH018": "In use may form flammable/explosive vapour-air mixture",
            "EUH019": "May form explosive peroxides",
            "EUH044": "Risk of explosion if heated under confinement",
        },
        routes=(),
        route_why="",
        controls=(NO_FLAMES, WATER_BATH),
        control_why="the hazard is ignition or a heated closed vessel, so ignition sources go and heating is "
                    "temperature-controlled and vented",
        risks=(FIRE, RUNAWAY),
        risk_why="the statement names an explosive mixture or an explosion on heating",
        prevention="Check the date on the bottle and test for peroxides before distilling; never distil to dryness; "
                   "never heat a closed vessel.",
        review="Peroxide former — check the opening date and test for peroxides before any distillation or "
               "concentration.",
    ),
    _Class(
        name="Supplemental EU statements: skin and airway effects",
        codes={
            "EUH066": "Repeated exposure may cause skin dryness or cracking",
            "EUH071": "Corrosive to the respiratory tract",
        },
        routes=(SKIN, INHALATION),
        route_why="the two statements name the skin and the respiratory tract directly",
        controls=(GLOVES, FUMEHOOD),
        control_why="barrier for the skin, containment for anything that reaches the airway",
    ),
)


def _build() -> Dict[str, Rule]:
    rules: Dict[str, Rule] = {}
    for klass in _CLASSES:
        for code, wording in klass.codes.items():
            quoted = f'{code} ("{wording}")'
            rules[code] = Rule(
                code=code,
                wording=wording,
                hazard_class=klass.name,
                routes=klass.routes,
                route_why=f"{quoted}: {klass.route_why}" if klass.route_why else "",
                controls=klass.controls,
                control_why=f"{quoted}: {klass.control_why}" if klass.control_why else "",
                risks=klass.risks,
                risk_why=f"{quoted}: {klass.risk_why}" if klass.risk_why else "",
                prevention=klass.prevention,
                review=f"{code}: {klass.review}" if klass.review else "",
            )
    return rules


RULES: Dict[str, Rule] = _build()


# --------------------------------------------------------------------------
# Codes as they actually arrive
# --------------------------------------------------------------------------

_CODE_RE = re.compile(r"^(EUH|H)\s*(\d{3})([A-Za-z]*)$", re.IGNORECASE)


def normalise_code(code: str) -> str:
    """
    'h315:' -> 'H315'. Returns '' for anything that is not a hazard statement code.

    Left deliberately strict: a code this cannot parse is reported as unknown
    rather than guessed at, because a guessed H number on a signed form is worse
    than a gap somebody has to fill.
    """
    match = _CODE_RE.match((code or "").strip().rstrip(":;,.").replace(" ", ""))
    if not match:
        return ""
    prefix, digits, suffix = match.groups()
    return f"{prefix.upper()}{digits}{suffix}"


def expand_codes(codes: Iterable[str]) -> Tuple[str, ...]:
    """
    Flatten 'H302 + H332' into its parts and keep the order, without duplicates.

    PubChem publishes combined acute-toxicity codes as one string. They mean
    exactly their components, so splitting them loses nothing and means the
    table does not need an entry per combination.
    """
    out: List[str] = []
    for raw in codes or ():
        for part in re.split(r"\s*\+\s*", str(raw or "")):
            code = normalise_code(part)
            if code and code not in out:
                out.append(code)
    return tuple(out)


def lookup(code: str) -> Optional[Rule]:
    """
    The rule for a code, following GHS subdivision letters back to their parent.

    H360FD, H350i and H361d are the parent hazard with the affected endpoint or
    route spelled out. The parent's ticks are right for all of them, so the
    suffix is dropped rather than treated as an unknown code.
    """
    code = normalise_code(code)
    if not code:
        return None
    if code in RULES:
        return RULES[code]
    stem = re.sub(r"[A-Za-z]+$", "", code)
    return RULES.get(stem)


# The safety net for a code with no rule: tick what its family implies and say
# out loud that a person has to look at it. GHS numbers the families, so the
# first digit is enough to be usefully cautious without pretending to know more.
_FALLBACK: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...], Tuple[str, ...], str]] = {
    # first digit: (routes, controls, risks, why)
    "2": ((EYES, SKIN), (NO_FLAMES,), (FIRE,),
          "an H2xx code is a physical hazard — fire, explosion or pressure — so ignition sources are removed and "
          "the fire question is answered yes until someone reads the actual code"),
    "3": ((SKIN, INHALATION, INGESTION), (GLOVES, FUMEHOOD), (),
          "an H3xx code is a health hazard, and with the specific code unrecognised every route of entry is "
          "assumed until someone reads it"),
    "4": ((), (), (),
          "an H4xx code is an environmental hazard: it changes where the waste goes, not what is worn"),
}


def _family(code: str) -> Tuple[Tuple[str, ...], Tuple[str, ...], Tuple[str, ...], str]:
    """The cautious defaults for a code with no rule, from its GHS number block."""
    digits = re.search(r"(\d)", code or "")
    # An unrecognised EUH statement is supplemental to a health or physical hazard and
    # its number block means nothing on its own, so it falls to the health defaults.
    if not digits or (code or "").upper().startswith("EUH"):
        return _FALLBACK["3"]
    return _FALLBACK.get(digits.group(1), _FALLBACK["3"])


# --------------------------------------------------------------------------
# Exposure routes and control measures
# --------------------------------------------------------------------------

def exposure_routes(codes: Iterable[str]) -> Dict[str, Tick]:
    """
    Which of Eyes / Skin / Inhalation / Ingestion to tick, and why.

    Returns only the routes that are ticked, keyed by the template's own label,
    in the template's order. A route ticked by several codes keeps all of them
    on the one `Tick` so the row can be defended from any of them.
    """
    reasons: Dict[str, List[Tuple[str, str]]] = {r: [] for r in EXPOSURE_ROUTES}
    for code in expand_codes(codes):
        rule = lookup(code)
        if rule:
            for route in rule.routes:
                reasons[route].append((code, rule.route_why))
            continue
        routes, _c, _r, why = _family(code)
        for route in routes:
            reasons[route].append((code, f"{code} is not in the rule table: {why}"))

    out: Dict[str, Tick] = {}
    for route in EXPOSURE_ROUTES:
        hits = reasons[route]
        if hits:
            out[route] = Tick(option=route,
                              why=" ".join(why for _code, why in hits),
                              codes=tuple(code for code, _why in hits))
    return out


def control_measures(codes: Iterable[str], *, procedure: str = "",
                     always_on: bool = True) -> Dict[str, Tick]:
    """
    Which of the eleven control measures to tick, and why.

    `always_on` keeps the three the blank template already ticks on every row.
    `procedure` is the lab-manual text, read only for the two controls no hazard
    code can imply — dropwise addition and a temperature-controlled bath are
    instructions in the method, not properties of a substance.
    """
    reasons: Dict[str, List[Tuple[str, str]]] = {c: [] for c in CONTROL_MEASURES}

    if always_on:
        for option in ALWAYS_ON:
            reasons[option].append(("", ALWAYS_ON_WHY))

    for code in expand_codes(codes):
        rule = lookup(code)
        if rule:
            for option in rule.controls:
                reasons[option].append((code, rule.control_why))
            continue
        _routes, controls, _risks, why = _family(code)
        for option in controls:
            reasons[option].append((code, f"{code} is not in the rule table: {why}"))

    for option, why in _procedure_controls(procedure):
        reasons[option].append(("", why))

    out: Dict[str, Tick] = {}
    for option in CONTROL_MEASURES:
        hits = reasons[option]
        if hits:
            out[option] = Tick(option=option,
                               why=" ".join(dict.fromkeys(why for _c, why in hits)),
                               codes=tuple(c for c, _w in hits if c))
    return out


# --------------------------------------------------------------------------
# Signals that live in the method, not on the bottle
#
# Four of this form's answers cannot come from a hazard code at all: whether the
# reaction runs away, whether it evolves gas, whether the room will smell, and
# which waste bottles get filled. Those are properties of the procedure. The
# patterns below are read against the lab manual text. They are matched, never
# executed, and they only ever add a tick or a line to review.
# --------------------------------------------------------------------------

_PROCEDURE_CONTROLS: Tuple[Tuple[str, str, str], ...] = (
    (ADD_DROPWISE, r"\bdrop-?wise\b|\badd(?:ed|ing)?\s+slowly\b|\bover\s+\d+\s*(?:min|h)",
     "the method itself says the addition is slow or dropwise, which is a rate control and belongs on the form"),
    (WATER_BATH, r"\bwater\s*bath\b|\boil\s*bath\b|\bheat(?:ed|ing)?\s+to\s+\d|\breflux",
     "the method heats the reaction, so the bath is the controlled way to do it"),
    (FUMEHOOD, r"\bfume\s*(?:hood|cupboard)\b|\bunder\s+nitrogen\b|\bunder\s+argon\b|\bSchlenk\b",
     "the method already places the work in a hood or on a line"),
    (NO_AIR, r"\bair-?sensitive\b|\bunder\s+(?:nitrogen|argon)\b|\bglove\s*box\b|\bSchlenk\b|\bdegass?ed\b",
     "the method calls for an inert atmosphere, so air exclusion is part of the procedure"),
)


def _procedure_controls(procedure: str) -> List[Tuple[str, str]]:
    text = procedure or ""
    return [(option, why) for option, pattern, why in _PROCEDURE_CONTROLS
            if re.search(pattern, text, re.IGNORECASE)]


_PROCEDURE_RISKS: Tuple[Tuple[str, str, str, str], ...] = (
    (RUNAWAY, r"\bexotherm|\bice\s*bath\b|\bcool(?:ed|ing)?\s+to\s+(?:0|-\d)|\b-78\b|\bdry\s*ice\b",
     "the method cools the reaction or calls the step exothermic, which is a statement that the heat has to go "
     "somewhere",
     "Add at a rate the cooling can keep up with; keep a thermometer in the flask and stop the addition if the "
     "temperature climbs."),
    (GAS, r"\beffervesc|\bgas\s+(?:is\s+)?evolv|\bevolution\s+of\s+(?:gas|hydrogen|nitrogen)|\bbubbl|\bCO2\b|"
          r"\bcarbon\s+dioxide\s+is\s+(?:evolved|released)|\bvent(?:ed|ing)\b",
     "the method describes gas coming off",
     "Vent the apparatus; never seal it; keep the sash low while gas is evolving."),
    (FIRE, r"\bnaked\s+flame\b|\bBunsen\b|\bdistil",
     "the method involves an open flame or a distillation",
     "No open flame near solvent; distil behind a screen with a bleed of inert gas and never to dryness."),
)


_MALODOROUS_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (r"\bthiol\b|\bmercapto|\bmercaptan\b|-SH\b", "thiols are detectable at parts per billion and the smell "
                                                  "carries to the corridor"),
    (r"\bsulf[ai]de\b|\bsulph[ai]de\b|\bthio(?:phenol|urea|acet)", "sulfides and thio- compounds smell strongly "
                                                                   "and cling to glassware"),
    (r"\bdimethyl\s+sulfide\b|\bDMS\b|\bSwern\b", "a Swern oxidation releases dimethyl sulfide, which is the "
                                                  "classic teaching-lab smell complaint"),
    (r"\bpyridine\b|\bquinoline\b", "pyridine and its relatives smell at very low concentration"),
    (r"\btri(?:ethyl|methyl)amine\b|\bmethylamine\b|\bdiethylamine\b|\bputrescine\b|\bcadaverine\b",
     "volatile low-molecular-weight amines smell of fish and persist on skin and clothing"),
    (r"\bisocyanide\b|\bisonitrile\b", "isocyanides are among the worst-smelling compounds routinely made"),
    (r"\bbutyric\s+acid\b|\bvaleric\s+acid\b|\bpropionic\s+acid\b|\bcaproic\s+acid\b",
     "short-chain carboxylic acids smell of rancid butter and sweat"),
    (r"\bphosphine\b|\bselen", "phosphines and selenium compounds have a persistent garlic smell and are toxic "
                               "as well as malodorous"),
    (r"\bacetic\s+anhydride\b|\bacid\s+chloride\b|\bacetyl\s+chloride\b|\bthionyl\s+chloride\b",
     "acid chlorides and anhydrides fume and are pungent"),
)


def malodorous(text: str) -> Optional[Tuple[str, str]]:
    """
    Whether the substance or method names something the room will smell.

    There is no GHS code for "smells". The form asks anyway, because a smell
    that reaches the corridor becomes everybody's problem, so this is a named
    list rather than a derivation, and it is matched against substance names and
    the method together.
    """
    for pattern, why in _MALODOROUS_PATTERNS:
        if re.search(pattern, text or "", re.IGNORECASE):
            return (why, re.search(pattern, text, re.IGNORECASE).group(0))
    return None


# --------------------------------------------------------------------------
# Waste
#
# The streams are the bottles in the corridor, so the mapping is by substance,
# not by hazard code. It is a named list because "is this halogenated" is a
# question about the molecule and a name is the only handle this module has.
# Anything unrecognised goes to Named Waste with a review line: an unlabelled
# bottle is the worst outcome, and Named Waste is where it is meant to go.
# --------------------------------------------------------------------------

_WASTE_BY_NAME: Tuple[Tuple[str, str, str], ...] = (
    # (stream, name pattern, why)
    (HALOGENATED,
     r"\bdichloromethane\b|\bmethylene\s+chloride\b|\bDCM\b|\bchloroform\b|\bcarbon\s+tetrachloride\b|"
     r"\btetrachloromethane\b|\b1,2-dichloroethane\b|\bchlorobenzene\b|\bdichlorobenzene\b|"
     r"\btrichloroethylene\b|\bbromobenzene\b|\bbromoethane\b|\biodomethane\b|\bmethyl\s+iodide\b|"
     r"\bfluorobenzene\b|\btrifluoroacetic\s+acid\b|\bTFA\b|\bhexafluoro|\bfreon\b|\bCDCl3\b|"
     r"\bdeuterated\s+chloroform\b",
     "a carbon-halogen bond puts it in the halogenated bottle, which is incinerated differently and must not be "
     "contaminated with the hydrocarbon stream"),
    (AQUEOUS,
     r"\bwater\b|\baqueous\b|\bbrine\b|\bhydrochloric\s+acid\b|\bsulfuric\s+acid\b|\bsulphuric\s+acid\b|"
     r"\bnitric\s+acid\b|\bsodium\s+hydroxide\b|\bpotassium\s+hydroxide\b|\bsodium\s+bicarbonate\b|"
     r"\bsodium\s+hydrogen\s*carbonate\b|\bammonium\s+chloride\b|\bsodium\s+chloride\b|\bD2O\b|"
     r"\bammonia\s+solution\b",
     "a water-based solution or a mineral acid or base goes to the aqueous bottle after neutralisation"),
    (HYDROCARBON,
     r"\bhexane\b|\bheptane\b|\bpentane\b|\bpetroleum\s+ether\b|\bpet\.?\s*ether\b|\btoluene\b|\bxylene\b|"
     r"\bbenzene\b|\bdiethyl\s+ether\b|\bether\b|\bTHF\b|\btetrahydrofuran\b|\bethyl\s+acetate\b|\bEtOAc\b|"
     r"\bacetone\b|\bmethanol\b|\bMeOH\b|\bethanol\b|\bEtOH\b|\bisopropanol\b|\bpropan-2-ol\b|\bIPA\b|"
     r"\bacetonitrile\b|\bMeCN\b|\bDMF\b|\bdimethylformamide\b|\bDMSO\b|\bdimethyl\s+sulfoxide\b|"
     r"\bdioxane\b|\bMTBE\b|\bcyclohexane\b|\btert-butanol\b|\bpyridine\b",
     "a non-halogenated organic solvent goes to the hydrocarbon bottle; this stream is only clean if nothing "
     "chlorinated goes in it"),
    (NAMED_WASTE,
     r"\bchromium\b|\bchromate\b|\bdichromate\b|\bosmium\b|\bOsO4\b|\bmercury\b|\blead\b|\bcadmium\b|"
     r"\bnickel\b|\bpalladium\b|\bPd/C\b|\bplatinum\b|\bsilver\b|\bcopper\b|\bcobalt\b|\bmanganese\b|"
     r"\bcyanide\b|\bazide\b|\bperoxide\b|\bhydrofluoric\b|\bHF\b|\bbromine\b|\bmercur",
     "heavy metals, cyanides, azides, peroxides and HF each need their own labelled container and must never "
     "be tipped into a mixed stream"),
)

_WASTE_BY_PROCEDURE: Tuple[Tuple[str, str, str], ...] = (
    (SILICA_TLC,
     r"\bsilica\b|\bcolumn\s+chromatograph|\bflash\s+chromatograph|\bTLC\b|\bthin[- ]layer\b|\bplate[s]?\s+were\s+"
     r"(?:run|visualis)",
     "the method runs a column or TLC, so there is loaded silica and there are used plates"),
    (CONTAMINATED_SOLID,
     r"\bcelite\b|\bfilter(?:ed|ing)?\b|\bmagnesium\s+sulfate\b|\bMgSO4\b|\bsodium\s+sulfate\b|\bNa2SO4\b|"
     r"\bdrying\s+agent\b|\bfrit\b|\bsinter\b|\bpipette\b",
     "filter cake, spent drying agent and contaminated disposables are solid waste carrying the reaction on them, "
     "not general rubbish"),
)

_HALOGENS = ("Cl", "Br", "I", "F")
_METALS = ("Na", "K", "Li", "Mg", "Ca", "Al", "Fe", "Cu", "Zn", "Ag", "Pd", "Pt",
           "Ni", "Co", "Mn", "Cr", "Hg", "Pb", "Cd", "Os", "Sn", "Ti", "Ru", "Rh")


def _formula_stream(formula: str) -> Optional[Tuple[str, str]]:
    """
    A second opinion on the waste stream from the molecular formula.

    Names lie — "TFA", a trade name, a typo — but a formula does not. This only
    ever adds a stream; it never removes one a name has already argued for.
    """
    if not formula:
        return None
    tokens = re.findall(r"[A-Z][a-z]?", formula)
    if "C" in tokens and any(h in tokens for h in _HALOGENS):
        return (HALOGENATED,
                f"the formula {formula} has both carbon and a halogen, so it belongs in the halogenated bottle "
                f"whatever it is called")
    if any(m in tokens for m in _METALS):
        return (NAMED_WASTE,
                f"the formula {formula} contains a metal, and metal-bearing waste needs its own labelled container")
    return None


def waste_streams(substances: Sequence["SubstanceAssessment"] = (), *,
                  procedure: str = "",
                  formulae: Optional[Dict[str, str]] = None) -> Tuple[Dict[str, Tick], Tuple[str, ...]]:
    """
    Which waste bottles this experiment fills, and what still needs deciding.

    Returns (ticks, review). A substance that matches nothing is not silently
    dropped: it goes to Named Waste and its name appears in `review`, because a
    bottle nobody labelled is the failure this form exists to prevent.
    """
    formulae = formulae or {}
    reasons: Dict[str, List[str]] = {stream: [] for stream in WASTE_STREAMS}
    review: List[str] = []

    for substance in substances:
        name = substance.name or ""
        matched = False
        for stream, pattern, why in _WASTE_BY_NAME:
            if re.search(pattern, name, re.IGNORECASE):
                reasons[stream].append(f"{name}: {why}")
                matched = True
        by_formula = _formula_stream(formulae.get(name, ""))
        if by_formula:
            stream, why = by_formula
            if why not in reasons[stream]:
                reasons[stream].append(f"{name}: {why}")
            matched = True
        if not matched:
            reasons[NAMED_WASTE].append(
                f"{name}: not recognised as a standard solvent or reagent, so it goes to named waste until "
                f"somebody says otherwise")
            review.append(
                f"Waste stream for {name} was not recognised — label its container by name and check with a "
                f"technician which stream it belongs to.")
        for code in substance.codes:
            rule = lookup(code)
            if rule and rule.hazard_class.startswith("Hazardous to the aquatic"):
                reasons[NAMED_WASTE].append(
                    f"{name}: {code} makes it hazardous to aquatic life, so nothing containing it — including "
                    f"the rinsings — goes down the sink")

    for stream, pattern, why in _WASTE_BY_PROCEDURE:
        if re.search(pattern, procedure or "", re.IGNORECASE):
            reasons[stream].append(why)

    ticks = {stream: Tick(option=stream, why=" ".join(dict.fromkeys(hits)))
             for stream in WASTE_STREAMS if (hits := reasons[stream])}
    return ticks, tuple(review)


# --------------------------------------------------------------------------
# The four specific-risk questions
# --------------------------------------------------------------------------

def specific_risks(substances: Sequence["SubstanceAssessment"] = (), *,
                   procedure: str = "") -> Dict[str, RiskRow]:
    """
    The Fire / Thermal Runaway / Gas Release / Malodorous rows, with prevention text.

    Every row is returned, ticked or not, so the caller can write "no" honestly
    rather than leaving a blank that reads as "not considered". `Special
    measures:` is returned unticked with no text: it is the chemist's box.
    """
    reasons: Dict[str, List[str]] = {row: [] for row in RISK_ROWS}
    codes_for: Dict[str, List[str]] = {row: [] for row in RISK_ROWS}
    prevention: Dict[str, List[str]] = {row: [] for row in RISK_ROWS}

    for substance in substances:
        for code in substance.codes:
            rule = lookup(code)
            if not rule:
                # An unrecognised code still answers the fire question if its number
                # block is the physical-hazard block. Better a "yes" somebody strikes
                # out than a "no" nobody thought about.
                _r, _c, rows, why = _family(code)
                for row in rows:
                    reasons[row].append(f"{substance.name}: {code} is not in the rule table: {why}")
                    codes_for[row].append(code)
                continue
            for row in rule.risks:
                reasons[row].append(f"{substance.name}: {rule.risk_why}")
                codes_for[row].append(code)
                if rule.prevention:
                    prevention[row].append(rule.prevention)

        smell = malodorous(substance.name)
        if smell:
            why, hit = smell
            reasons[MALODOROUS].append(f"{substance.name} ({hit}): {why}")
            prevention[MALODOROUS].append(
                "Keep every transfer and every quench inside the fume hood with the sash low; rinse glassware "
                "into a sealed quench (bleach for thiols and sulfides) before it leaves the hood.")

    for row, pattern, why, advice in _PROCEDURE_RISKS:
        if re.search(pattern, procedure or "", re.IGNORECASE):
            reasons[row].append(f"the method: {why}")
            prevention[row].append(advice)

    smell = malodorous(procedure)
    if smell and not reasons[MALODOROUS]:
        why, hit = smell
        reasons[MALODOROUS].append(f"the method mentions {hit}: {why}")
        prevention[MALODOROUS].append(
            "Keep every transfer and every quench inside the fume hood with the sash low.")

    out: Dict[str, RiskRow] = {}
    for row in RISK_ROWS:
        if row == SPECIAL:
            out[row] = RiskRow(row=row, ticked=False, prevention="", why=
                               "left for the chemist: anything this form has no box for — cylinder restraint, "
                               "out-of-hours working, a second person present — goes here")
            continue
        hits = list(dict.fromkeys(reasons[row]))
        out[row] = RiskRow(
            row=row,
            ticked=bool(hits),
            prevention=" ".join(dict.fromkeys(prevention[row])) if hits else "",
            why=" ".join(hits) if hits else f"nothing in the substances or the method argues for {row.lower()}",
            codes=tuple(dict.fromkeys(codes_for[row])),
        )
    return out


# --------------------------------------------------------------------------
# Top level
# --------------------------------------------------------------------------

_NO_DATA_REVIEW = (
    "No GHS classification was found for {name}. That is not the same as safe — it usually means nobody has "
    "notified it. Read the supplier's safety data sheet and fill this row in by hand before the form is signed."
)

_NO_DATA_HAZARDS_TEXT = "NO CLASSIFICATION FOUND — assess from the supplier SDS before use"


def assess_substance(hazard: Optional[Dict] = None, *, name: str = "", cas: str = "",
                     amount: str = "", procedure: str = "") -> SubstanceAssessment:
    """
    One substance row, from a `safety.hazards()` result.

    `hazard` is exactly what `safety.hazards(name, cas)` returns; pass None to
    assess a substance that was never looked up, which is treated the same as a
    lookup that found nothing. When there is no classification the row is filled
    with the standing controls only, is marked in `review`, and its hazards cell
    says so in capitals rather than sitting empty.
    """
    hazard = hazard or {}
    name = name or hazard.get("name") or ""
    cas = cas or hazard.get("cas") or ""
    primary = hazard.get("primary") or {}
    published = tuple(h.get("code", "") for h in primary.get("hazards", []) if h.get("code"))
    codes = expand_codes(published)

    if not hazard.get("found") or not codes:
        return SubstanceAssessment(
            name=name, cas=cas, amount=amount, classified=False,
            hazards_text=_NO_DATA_HAZARDS_TEXT,
            codes=(), unknown_codes=(),
            exposure={},
            controls=control_measures((), procedure=procedure),
            risks=(),
            review=(_NO_DATA_REVIEW.format(name=name or "this substance"),),
            source=primary.get("source", ""), url=hazard.get("url") or "",
        )

    unknown = tuple(code for code in codes if lookup(code) is None)
    review: List[str] = []
    for code in codes:
        rule = lookup(code)
        if rule and rule.review:
            review.append(rule.review)
    for code in unknown:
        review.append(
            f"{code} has no rule in this table, so the form has been ticked cautiously from its hazard family "
            f"only. Read the statement on the SDS and correct this row by hand.")

    texts = {h.get("code"): h.get("text", "") for h in primary.get("hazards", [])}
    hazards_text = "; ".join(
        f"{code} {texts.get(code) or (lookup(code).wording if lookup(code) else '')}".strip()
        for code in codes)

    risk_rows = tuple(
        RiskRow(row=row, ticked=True, prevention=lookup(code).prevention if lookup(code) else "",
                why=lookup(code).risk_why if lookup(code) else "", codes=(code,))
        for code in codes
        for row in (lookup(code).risks if lookup(code) else ()))

    return SubstanceAssessment(
        name=name, cas=cas, amount=amount, classified=True,
        hazards_text=hazards_text, codes=codes, unknown_codes=unknown,
        exposure=exposure_routes(codes),
        controls=control_measures(codes, procedure=procedure),
        risks=risk_rows,
        review=tuple(dict.fromkeys(review)),
        source=primary.get("source", ""), url=hazard.get("url") or "",
    )


def assess_form(hazards: Sequence[Dict] = (), *, names: Sequence[str] = (),
                amounts: Optional[Dict[str, str]] = None,
                formulae: Optional[Dict[str, str]] = None,
                procedure: str = "") -> FormAssessment:
    """
    A whole form: one row per substance, plus the risk questions and the waste.

    `hazards` is a list of `safety.hazards()` results. `names` is only needed for
    substances that were never looked up, so that a substance mentioned in the
    method still gets a row saying it was not assessed rather than vanishing.
    """
    amounts = amounts or {}
    rows: List[SubstanceAssessment] = [
        assess_substance(h, amount=amounts.get(h.get("name", ""), ""), procedure=procedure)
        for h in hazards]
    assessed = {row.name.strip().lower() for row in rows}
    for name in names:
        if name.strip().lower() not in assessed:
            rows.append(assess_substance(None, name=name, amount=amounts.get(name, ""),
                                         procedure=procedure))

    waste, waste_review = waste_streams(rows, procedure=procedure, formulae=formulae)
    review = list(waste_review)
    for row in rows:
        review.extend(f"{row.name}: {line}" for line in row.review)
    review.append(
        "Approved By and the date are deliberately left blank: a competent person signs this form, not the tool "
        "that drafted it.")

    return FormAssessment(
        substances=tuple(rows),
        risks=specific_risks(rows, procedure=procedure),
        waste=waste,
        review=tuple(dict.fromkeys(review)),
    )
