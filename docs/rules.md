# The rules

`coshh/rules.py` is the argument the form makes. Everything else in this repo
fetches data or writes XML; this is the part that decides what gets ticked, so
it is the part a demonstrator should be able to read and disagree with.

## What the form will accept

The *COSHH Form, Chemistry Teaching Laboratory* asks closed questions.
Per substance: which of **four exposure routes** apply, and which of **eleven
control measures** are in use. Per experiment: **four yes/no risk questions**,
and which of **six waste streams** get filled. There is nowhere to write "it
depends", so every rule below ends in one of those boxes.

| group | options |
|---|---|
| Exposure routes | Eyes, Skin, Inhalation, Ingestion |
| Control measures | spill advice, Safety spectacles, Lab coat, Gloves, Fumehood, Keep away from naked flames and sources of ignition, Heat using temperature-controlled water bath, Not to be used if pregnant, Do not store or use near water (store in oil), Add dropwise to solution, Do not expose to air |
| Risk rows | Fire or Explosion, Thermal Runaway, Gas Release, Malodorous Substances, Special measures |
| Waste | Halogenated, Aqueous, Hydrocarbon, Named Waste, Contaminated solid waste, Silica/TLC |

## The three commitments

**Every tick carries a reason.** A `Tick` holds the option, the codes that drove
it, and a sentence written from the code's own published wording. `H314` ticks
Eyes and Skin because its statement is "Causes severe skin burns and eye
damage", not because nitric acid is nasty. If the reason cannot be written, the
rule does not go in the table.

**Conservative when unsure.** An unrecognised code is not skipped: it takes its
GHS number block's cautious defaults — H2xx removes ignition sources and answers
the fire question yes, H3xx assumes every route of entry and ticks gloves and
the fume hood — *and* the substance goes on the `review` list saying the code
was not recognised. A substance PubChem holds no classification for gets
`NO CLASSIFICATION FOUND — assess from the supplier SDS before use` in its
hazards cell, in capitals, so a blank row can never be mistaken for a safe one.

**Judgement stays with the chemist.** Scale, containment, the quench plan and
the "Approved By" signature are not derivable from an H number, so nothing here
derives them. `Special measures:` is returned deliberately unticked and empty,
and every generated form carries a review line saying the signature is not the
tool's to give.

## Standing controls

Three boxes are ticked on every row, on every form:

| option | why |
|---|---|
| In case of spill, consult a demonstrator… | the blank template already ticks it on rows 2–5; it is the lab's standing instruction, not a substance judgement |
| Safety spectacles | same: eye protection is worn at all times in this teaching lab |
| Lab coat | same |

`control_measures(..., always_on=False)` turns them off, which is only useful
for inspecting what a code contributes on its own.

## Codes as they actually arrive

| behaviour | example | why |
|---|---|---|
| normalisation | `" h315: "` → `H315` | PubChem's text carries punctuation and case |
| combined codes split | `H302 + H332` → `H302`, `H332` | a combined statement means exactly its parts, so the table needs no entry per combination |
| subdivision letters fall back | `H361d`, `H350i`, `H360FD` → `H361`, `H350`, `H360` | the suffix names the endpoint or route; the parent's ticks are right for all of them |
| unparseable input | `"corrosive"` → ignored, listed as unknown | a guessed H number on a signed form is worse than a gap someone has to fill |

## The table, class by class

Grouped by GHS hazard class, because the classes are what the codes mean. Each
table is generated from `coshh/rules.py`; the sentences under it are the `why`
strings the code carries at runtime.

### Explosives

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H200` | Unstable explosive | Eyes, Skin | no flames, water bath | Fire or Explosion, Thermal Runaway |
| `H201` | Explosive; mass explosion hazard | Eyes, Skin | no flames, water bath | Fire or Explosion, Thermal Runaway |
| `H202` | Explosive; severe projection hazard | Eyes, Skin | no flames, water bath | Fire or Explosion, Thermal Runaway |
| `H203` | Explosive; fire, blast or projection hazard | Eyes, Skin | no flames, water bath | Fire or Explosion, Thermal Runaway |
| `H204` | Fire or projection hazard | Eyes, Skin | no flames, water bath | Fire or Explosion, Thermal Runaway |
| `H205` | May mass explode in fire | Eyes, Skin | no flames, water bath | Fire or Explosion, Thermal Runaway |

- **Routes** — an explosion injures by blast and by fragments, which reach the eyes and any unprotected skin first.
- **Controls** — an explosive must be kept away from every ignition source, and any heating must go through a temperature-controlled bath rather than a flame or a hotplate where the temperature can run.
- **Risk rows** — the statement is itself a statement of explosion hazard.
- **Prevention text** — “Smallest workable quantity behind a blast screen; no ignition sources; temperature-controlled heating only.”
- **Review line** — Explosive classification — agree the scale, the screening and who is present with a demonstrator before any of this is weighed out.

### Self-reactive substances and organic peroxides

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H240` | Heating may cause an explosion | Eyes, Skin | no flames, water bath | Fire or Explosion, Thermal Runaway |
| `H241` | Heating may cause a fire or explosion | Eyes, Skin | no flames, water bath | Fire or Explosion, Thermal Runaway |
| `H242` | Heating may cause a fire | Eyes, Skin | no flames, water bath | Fire or Explosion, Thermal Runaway |

- **Routes** — the failure mode is a fire or an explosion at the bench, which reaches eyes and skin.
- **Controls** — the code names heating as the trigger, so heating is the thing to control: a bath with a set temperature, never an open flame.
- **Risk rows** — 'heating may cause' is the definition of a runaway that ends in fire or explosion.
- **Prevention text** — “Temperature-controlled bath with the set point recorded; no direct flame; do not exceed the self-accelerating decomposition temperature on the SDS.”
- **Review line** — Self-reactive or peroxide — check the self-accelerating decomposition temperature on the SDS and keep the working temperature well below it.

### Self-reactives that do not need air

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H230` | May react explosively even in the absence of air | Eyes, Skin | no flames, water bath | Fire or Explosion, Thermal Runaway |
| `H231` | May react explosively even in the absence of air at elevated pressure and/or temperature | Eyes, Skin | no flames, water bath | Fire or Explosion, Thermal Runaway |

- **Routes** — an explosive decomposition injures by blast and fragments.
- **Controls** — inerting does not help here — the code says so — so the controls left are ignition sources and controlled heating.
- **Risk rows** — an explosive reaction that does not need air cannot be stopped by blanketing it.
- **Prevention text** — “Keep below the pressure and temperature limits on the SDS; inert atmosphere is not a control here.”
- **Review line** — Reacts explosively without air — an inert blanket is not protection. Confirm the temperature and pressure limits with a demonstrator.

### Flammable gases and aerosols

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H220` | Extremely flammable gas | Inhalation | no flames, fumehood | Fire or Explosion, Gas Release |
| `H221` | Flammable gas | Inhalation | no flames, fumehood | Fire or Explosion, Gas Release |
| `H222` | Extremely flammable aerosol | Inhalation | no flames, fumehood | Fire or Explosion, Gas Release |
| `H223` | Flammable aerosol | Inhalation | no flames, fumehood | Fire or Explosion, Gas Release |

- **Routes** — it is released as a gas or a spray, so it is in the air you are standing in.
- **Controls** — a flammable gas needs every ignition source removed and needs extraction so it cannot build to its lower explosive limit in the room.
- **Risk rows** — the substance is a gas and it burns.
- **Prevention text** — “Fume hood with the sash low; no naked flames or hot surfaces; cylinder secured and the line leak-checked before use.”

### Flammable liquids

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H224` | Extremely flammable liquid and vapour | Skin, Inhalation | no flames, water bath, fumehood | Fire or Explosion |
| `H225` | Highly flammable liquid and vapour | Skin, Inhalation | no flames, water bath, fumehood | Fire or Explosion |
| `H226` | Flammable liquid and vapour | Skin, Inhalation | no flames, water bath, fumehood | Fire or Explosion |
| `H227` | Combustible liquid | Skin, Inhalation | no flames, water bath, fumehood | Fire or Explosion |

- **Routes** — the statement says 'liquid and vapour': there is vapour above it at room temperature, so it is breathed as well as touched.
- **Controls** — vapour travels to a distant ignition source, so flames go; if it must be heated it goes on a water bath, not a hotplate; and the hood keeps the vapour out of the room.
- **Risk rows** — the vapour, not the liquid, is what ignites, and it spreads.
- **Prevention text** — “Fume hood; no naked flames in the bay; heat only on a temperature-controlled water bath; keep the bottle closed when not pouring.”

### Flammable solids

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H228` | Flammable solid | Skin | no flames | Fire or Explosion |

- **Routes** — it is handled as a solid, so contact is the route that exists at the bench.
- **Controls** — the hazard is ignition, so the control is removing ignition sources.
- **Risk rows** — a flammable solid burns where it is spilled.
- **Prevention text** — “No ignition sources; sweep up spills immediately; do not grind or generate dust.”

### Pyrophoric substances

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H250` | Catches fire spontaneously if exposed to air | Skin | no air, no flames, gloves | Fire or Explosion, Thermal Runaway |

- **Routes** — it ignites on contact with air, so the injury is a burn where it touches.
- **Controls** — the code names air as the trigger, so air exclusion is the control; gloves because a syringe or cannula transfer puts your hands next to the thing that lights on contact.
- **Risk rows** — spontaneous ignition is a fire with no ignition source to remove.
- **Prevention text** — “Schlenk line or glovebox; septum and cannula or syringe transfer under inert gas; quench waste and needles deliberately, never in the bin.”
- **Review line** — Pyrophoric — do not run this unsupervised. Agree the transfer and the quench with a demonstrator, and have dry sand to hand.

### Self-heating substances

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H251` | Self-heating; may catch fire | Skin | no air, no flames | Fire or Explosion, Thermal Runaway |
| `H252` | Self-heating in large quantities; may catch fire | Skin | no air, no flames | Fire or Explosion, Thermal Runaway |

- **Routes** — the hazard is a burn from material that has heated itself where it sits.
- **Controls** — self-heating is oxidation by air, so keeping it sealed is the control, and ignition sources go because the end point is a fire.
- **Risk rows** — self-heating is a runaway by definition: the reaction supplies its own heat.
- **Prevention text** — “Keep the container closed and in small quantities; do not pile up used filter cake or wipes; do not leave residues on the bench overnight.”
- **Review line** — Self-heating — the residue and the waste are as much of a fire risk as the bottle. Agree how the waste is quenched and stored.

### Substances which in contact with water emit flammable gases

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H260` | In contact with water releases flammable gases which may ignite spontaneously | Eyes, Skin | not near water, no flames, gloves, dropwise | Fire or Explosion, Gas Release |
| `H261` | In contact with water releases flammable gas | Eyes, Skin | not near water, no flames, gloves, dropwise | Fire or Explosion, Gas Release |

- **Routes** — water on the skin or in the eye is enough to set it off, and a violent evolution of gas sprays what is in the flask.
- **Controls** — the code names water as the trigger, so water goes; the gas released is flammable, so ignition sources go; and any deliberate contact with water — the quench — is made dropwise so the gas comes off at a rate the apparatus can vent.
- **Risk rows** — the statement is a statement of gas evolution, and the gas burns.
- **Prevention text** — “Dry glassware and dry solvent; store under oil or inert gas; quench dropwise into a stirred quench at 0 °C behind a screen, with no flames in the bay.”
- **Review line** — Water-reactive — write the quench down before you start, including what you quench into and at what temperature, and have a demonstrator check it.

### Oxidising substances

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H270` | May cause or intensify fire; oxidizer | Eyes, Skin | no flames, gloves | Fire or Explosion |
| `H271` | May cause fire or explosion; strong oxidizer | Eyes, Skin | no flames, gloves | Fire or Explosion |
| `H272` | May intensify fire; oxidizer | Eyes, Skin | no flames, gloves | Fire or Explosion |

- **Routes** — strong oxidisers attack tissue on contact as well as feeding a fire.
- **Controls** — an oxidiser turns anything combustible nearby into the fuel, so it is kept away from ignition sources and from paper, solvent and glove boxes of tissue; gloves because contact damages skin.
- **Risk rows** — the code's own words: it causes or intensifies fire.
- **Prevention text** — “Keep away from organics, paper and solvent bottles; separate spatulas; no ignition sources; never return unused solid to the stock bottle.”
- **Review line** — Oxidiser — check nothing combustible is stored with it, and that the spatula is clean.

### Gases under pressure

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H280` | Contains gas under pressure; may explode if heated | Eyes, Skin | gloves | Fire or Explosion, Gas Release |
| `H281` | Contains refrigerated gas; may cause cryogenic burns or injury | Eyes, Skin | gloves | Fire or Explosion, Gas Release |

- **Routes** — a burst cylinder or a cryogenic splash injures eyes and skin directly.
- **Controls** — cryogenic and high-pressure transfers need the hands covered; the rest of the control is the cylinder restraint, which this form has no box for.
- **Risk rows** — a pressurised container that fails releases its whole contents at once.
- **Prevention text** — “Cylinder clamped and the valve capped when moving; regulator checked; never heat the cylinder; cryogenic gloves and a face shield for transfers.”
- **Review line** — Gas under pressure — the cylinder restraint and regulator are not on this form. Note them under Special measures.

### Corrosive to metals

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H290` | May be corrosive to metals | — | gloves | — |

- **Controls** — this code is about the apparatus rather than the person, but anything corrosive enough to eat a clamp is handled gloved.
- **Review line** — Corrosive to metals — use glass or PTFE, keep it off the clamps and the balance, and do not leave it in a metal-capped bottle.

### Acute toxicity, oral

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H300` | Fatal if swallowed | Ingestion | gloves | — |
| `H301` | Toxic if swallowed | Ingestion | gloves | — |
| `H302` | Harmful if swallowed | Ingestion | gloves | — |
| `H303` | May be harmful if swallowed | Ingestion | gloves | — |

- **Routes** — the statement's own words are 'if swallowed'.
- **Controls** — nobody drinks it deliberately — it is swallowed off a contaminated hand or a contaminated pen, so the glove is the control that actually interrupts the route.

### Acute toxicity, dermal

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H310` | Fatal in contact with skin | Skin | gloves | — |
| `H311` | Toxic in contact with skin | Skin | gloves | — |
| `H312` | Harmful in contact with skin | Skin | gloves | — |
| `H313` | May be harmful in contact with skin | Skin | gloves | — |

- **Routes** — the statement's own words are 'in contact with skin'.
- **Controls** — the route is the skin, so the control is the barrier on the skin.
- **Review line** — Toxic by skin contact — check the glove material against the SDS breakthrough table; nitrile is not right for everything.

### Acute toxicity, inhalation

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H330` | Fatal if inhaled | Inhalation | fumehood | — |
| `H331` | Toxic if inhaled | Inhalation | fumehood | — |
| `H332` | Harmful if inhaled | Inhalation | fumehood | — |
| `H333` | May be harmful if inhaled | Inhalation | fumehood | — |

- **Routes** — the statement's own words are 'if inhaled'.
- **Controls** — the route is the air, so the control is keeping it out of the air you are in.

### Aspiration hazard

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H304` | May be fatal if swallowed and enters airways | Ingestion, Inhalation | fumehood | — |
| `H305` | May be harmful if swallowed and enters airways | Ingestion, Inhalation | fumehood | — |

- **Routes** — the harm needs both steps the statement names: it is swallowed, then it enters the airways.
- **Controls** — the substances that carry this code are thin, volatile hydrocarbons, so the hood is already the right place for them.
- **Review line** — Aspiration hazard — never pipette by mouth, and if it is swallowed do not induce vomiting; say so when you call for help.

### Skin corrosion / serious eye damage

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H314` | Causes severe skin burns and eye damage | Eyes, Skin | gloves | — |

- **Routes** — the statement names both: skin burns and eye damage.
- **Controls** — a corrosive burns on contact, so the barrier goes on before the bottle is opened.
- **Review line** — Corrosive — know where the nearest eyewash and safety shower are before you start, and add corrosive to water, never water to corrosive.

### Skin irritation

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H315` | Causes skin irritation | Skin | gloves | — |
| `H316` | Causes mild skin irritation | Skin | gloves | — |

- **Routes** — the statement names the skin.
- **Controls** — the barrier is the control for a substance that damages skin on contact.

### Skin sensitisation

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H317` | May cause an allergic skin reaction | Skin | gloves | — |

- **Routes** — the statement names an allergic reaction of the skin.
- **Controls** — sensitisation has no safe contact dose, so the aim is no contact at all.
- **Review line** — Skin sensitiser — one exposure can sensitise you for life. Change gloves the moment they are splashed rather than at the end.

### Serious eye damage / eye irritation

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H318` | Causes serious eye damage | Eyes | gloves | — |
| `H319` | Causes serious eye irritation | Eyes | gloves | — |
| `H320` | Causes eye irritation | Eyes | gloves | — |

- **Routes** — the statement names the eye.
- **Controls** — what reaches an eye is a splash from a hand or a pipette, so the glove is part of keeping it away from the face; the spectacles are already ticked as standard.

### Respiratory sensitisation

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H334` | May cause allergy or asthma symptoms or breathing difficulties if inhaled | Inhalation | fumehood | — |

- **Routes** — the statement's own words are 'if inhaled'.
- **Controls** — a respiratory sensitiser has no safe airborne dose, so it stays in the hood at all times.
- **Review line** — Respiratory sensitiser — tell a demonstrator if you have asthma before handling this, and keep the sash as low as the work allows.

### Specific target organ toxicity, single exposure (irritation / narcosis)

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H335` | May cause respiratory irritation | Inhalation | fumehood | — |
| `H336` | May cause drowsiness or dizziness | Inhalation | fumehood | — |

- **Routes** — both effects are effects of breathing the vapour.
- **Controls** — the effect is caused by the vapour reaching you, so the hood is the control.

### Germ cell mutagenicity

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H340` | May cause genetic defects | Skin, Inhalation, Ingestion | gloves, fumehood, not if pregnant | — |
| `H341` | Suspected of causing genetic defects | Skin, Inhalation, Ingestion | gloves, fumehood, not if pregnant | — |

- **Routes** — a mutagenic effect is driven by dose, not by which door the dose came through, so every route that exists at the bench is ticked.
- **Controls** — the aim is no exposure by any route: barrier on the hands, containment for the vapour, and — because a germ cell mutagen acts on the material passed to a child — the pregnancy restriction.
- **Review line** — Mutagen — use the smallest quantity that works, keep it in the hood, and ask whether a less hazardous substitute would do the same job.

### Carcinogenicity

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H350` | May cause cancer | Skin, Inhalation, Ingestion | gloves, fumehood, not if pregnant | — |
| `H351` | Suspected of causing cancer | Skin, Inhalation, Ingestion | gloves, fumehood, not if pregnant | — |

- **Routes** — a carcinogenic effect is driven by cumulative dose by any route, so every route that exists at the bench is ticked.
- **Controls** — no threshold is assumed for a carcinogen, so contact and vapour are both engineered out, and the pregnancy restriction is ticked because this teaching lab restricts the whole CMR set.
- **Review line** — Carcinogen — named substance. Use the smallest quantity, keep it in the hood, and ask whether a substitute exists before ordering more.

### Reproductive toxicity

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H360` | May damage fertility or the unborn child | Skin, Inhalation, Ingestion | gloves, fumehood, not if pregnant | — |
| `H361` | Suspected of damaging fertility or the unborn child | Skin, Inhalation, Ingestion | gloves, fumehood, not if pregnant | — |
| `H362` | May cause harm to breast-fed children | Skin, Inhalation, Ingestion | gloves, fumehood, not if pregnant | — |

- **Routes** — the effect follows the dose that reaches the bloodstream, whichever route delivered it.
- **Controls** — this is the code the 'Not to be used if pregnant' box exists for, and the glove and the hood are what keep the dose at zero for everybody else.
- **Review line** — Reproductive toxin — if you are or may be pregnant or breast-feeding, speak to a demonstrator before this experiment rather than during it.

### Specific target organ toxicity, organ damage

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H370` | Causes damage to organs | Skin, Inhalation, Ingestion | gloves, fumehood | — |
| `H371` | May cause damage to organs | Skin, Inhalation, Ingestion | gloves, fumehood | — |
| `H372` | Causes damage to organs through prolonged or repeated exposure | Skin, Inhalation, Ingestion | gloves, fumehood | — |
| `H373` | May cause damage to organs through prolonged or repeated exposure | Skin, Inhalation, Ingestion | gloves, fumehood | — |

- **Routes** — organ damage follows the systemic dose, so every route that can deliver a dose is ticked.
- **Controls** — keep the systemic dose at zero: barrier on the hands and containment for anything airborne.
- **Review line** — Organ toxicity — read which organ is named on the SDS; for a repeated-exposure code it is the number of times you handle it that matters, not one session.

### Hazardous to the aquatic environment

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `H400` | Very toxic to aquatic life | — | — | — |
| `H401` | Toxic to aquatic life | — | — | — |
| `H402` | Harmful to aquatic life | — | — | — |
| `H410` | Very toxic to aquatic life with long-lasting effects | — | — | — |
| `H411` | Toxic to aquatic life with long-lasting effects | — | — | — |
| `H412` | Harmful to aquatic life with long-lasting effects | — | — | — |
| `H413` | May cause long-lasting harmful effects to aquatic life | — | — | — |
| `H420` | Harms public health and the environment by destroying ozone in the upper atmosphere | — | — | — |

- **Review line** — Hazardous to the environment — nothing containing this goes down the sink, including the rinsings. Collect it as named waste.

### Supplemental EU statements: reaction with water

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `EUH014` | Reacts violently with water | Eyes, Skin, Inhalation | not near water, fumehood, gloves, dropwise | Gas Release |
| `EUH029` | Contact with water liberates toxic gas | Eyes, Skin, Inhalation | not near water, fumehood, gloves, dropwise | Gas Release |

- **Routes** — a violent reaction sprays the contents at the face, and the gas released is breathed.
- **Controls** — water is the named trigger, the product is a gas that must stay in the hood, and any deliberate contact with water is made dropwise so the rate stays controllable.
- **Risk rows** — the statement is a statement about releasing gas.
- **Prevention text** — “Dry glassware; quench dropwise into a stirred, cooled quench inside the hood with the sash low.”
- **Review line** — Reacts with water — write the quench down before you start and have it checked.

### Supplemental EU statements: reaction with acid

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `EUH031` | Contact with acids liberates toxic gas | Inhalation | fumehood | Gas Release |
| `EUH032` | Contact with acids liberates very toxic gas | Inhalation | fumehood | Gas Release |

- **Routes** — the harm is the gas, and the gas is breathed.
- **Controls** — the gas has to be contained, and the hood is the only containment this form offers.
- **Risk rows** — the statement is a statement about releasing gas.
- **Prevention text** — “Keep acids out of this waste stream and out of the same spill tray; work in the hood.”
- **Review line** — Liberates toxic gas with acid — check nothing acidic shares the waste container or the spill tray.

### Supplemental EU statements: peroxide formation and confinement

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `EUH018` | In use may form flammable/explosive vapour-air mixture | — | no flames, water bath | Fire or Explosion, Thermal Runaway |
| `EUH019` | May form explosive peroxides | — | no flames, water bath | Fire or Explosion, Thermal Runaway |
| `EUH044` | Risk of explosion if heated under confinement | — | no flames, water bath | Fire or Explosion, Thermal Runaway |

- **Controls** — the hazard is ignition or a heated closed vessel, so ignition sources go and heating is temperature-controlled and vented.
- **Risk rows** — the statement names an explosive mixture or an explosion on heating.
- **Prevention text** — “Check the date on the bottle and test for peroxides before distilling; never distil to dryness; never heat a closed vessel.”
- **Review line** — Peroxide former — check the opening date and test for peroxides before any distillation or concentration.

### Supplemental EU statements: skin and airway effects

| code | statement | routes | controls | risk rows |
|---|---|---|---|---|
| `EUH066` | Repeated exposure may cause skin dryness or cracking | Skin, Inhalation | gloves, fumehood | — |
| `EUH071` | Corrosive to the respiratory tract | Skin, Inhalation | gloves, fumehood | — |

- **Routes** — the two statements name the skin and the respiratory tract directly.
- **Controls** — barrier for the skin, containment for anything that reaches the airway.

## Signals that live in the method, not on the bottle

Four of the form's answers cannot come from a hazard code at all. Whether the
reaction runs away, whether it evolves gas, whether the room will smell and
which bottles get filled are properties of the *procedure*. These patterns are
matched against the lab-manual text. They are matched, never executed, and they
can only ever add a tick or a review line — a procedure can make the assessment
more cautious, never less.

### Method → control measures

| control | triggered by | why |
|---|---|---|
| Add dropwise to solution | "dropwise", "added slowly", "over 30 min" | the method itself specifies a rate control, and the form has a box for it |
| Heat using temperature-controlled water bath | "water bath", "oil bath", "heated to 60", "reflux" | the method heats the reaction, so the bath is how it is done safely |
| Fumehood | "fume hood", "under nitrogen", "Schlenk" | the method already places the work in containment |
| Do not expose to air | "air-sensitive", "under argon", "glovebox", "degassed" | the method calls for an inert atmosphere |

### Method → risk rows

| row | triggered by | prevention text |
|---|---|---|
| Thermal Runaway | "exothermic", "ice bath", "cooled to 0 °C", "−78", "dry ice" | add at a rate the cooling can keep up with; thermometer in the flask; stop the addition if the temperature climbs |
| Gas Release | "effervescence", "gas is evolved", "bubbling", "vented" | vent the apparatus, never seal it, keep the sash low while gas is evolving |
| Fire or Explosion | "naked flame", "Bunsen", "distil" | no open flame near solvent; distil behind a screen, never to dryness |

### Malodorous substances

There is no GHS code for "smells", and the form asks anyway, because a smell
that reaches the corridor becomes everybody's problem. This one is a named list,
matched against substance names and the method together. Any hit ticks the row
and writes the same prevention sentence: keep every transfer and quench inside
the hood with the sash low, and quench thiols and sulfides into bleach before
the glassware leaves the hood.

| pattern | why |
|---|---|
| thiol, mercapto-, mercaptan, –SH | detectable at parts per billion; carries to the corridor |
| sulfide/sulphide, thiophenol, thiourea | strong and clings to glassware |
| dimethyl sulfide, DMS, Swern | a Swern oxidation releases DMS — the classic teaching-lab complaint |
| pyridine, quinoline | smell at very low concentration |
| triethylamine, methylamine, diethylamine, putrescine, cadaverine | volatile amines smell of fish and persist on skin and clothing |
| isocyanide, isonitrile | among the worst-smelling compounds routinely made |
| butyric / valeric / propionic / caproic acid | rancid butter and sweat |
| phosphine, selen- | persistent garlic smell, and toxic as well as malodorous |
| acetic anhydride, acid chloride, thionyl chloride | fume and are pungent |

## Waste

The streams are the bottles in the corridor, so the mapping is by substance, not
by hazard code — "is this halogenated" is a question about the molecule.

| stream | matched on | why |
|---|---|---|
| Halogenated | DCM, chloroform, CCl₄, 1,2-DCE, chlorobenzene, bromobenzene, MeI, TFA, CDCl₃… | a carbon–halogen bond; this stream is incinerated differently and must not be contaminated with the hydrocarbon one |
| Aqueous | water, brine, HCl, H₂SO₄, HNO₃, NaOH, KOH, NaHCO₃, NH₄Cl, D₂O | water-based solutions and mineral acids/bases, after neutralisation |
| Hydrocarbon | hexane, toluene, EtOAc, THF, Et₂O, acetone, MeOH, EtOH, MeCN, DMF, DMSO, dioxane, pyridine… | non-halogenated organics; only clean if nothing chlorinated goes in |
| Named Waste | Cr, Os, Hg, Pb, Cd, Ni, Pd/C, Ag, Cu, Co, Mn, cyanide, azide, peroxide, HF, Br₂ | each needs its own labelled container and must never be tipped into a mixed stream |
| Contaminated solid waste | "celite", "filtered", "MgSO₄", "Na₂SO₄", "drying agent", "frit", "pipette" in the method | filter cake, spent drying agent and disposables carry the reaction on them |
| Silica/TLC | "silica", "column chromatography", "TLC", "thin-layer" in the method | loaded silica and used plates |

Two safety nets:

- **The formula overrules an unhelpful name.** Given a molecular formula,
  carbon plus any of Cl/Br/I/F adds Halogenated, and any metal symbol adds Named
  Waste. Names lie — "Compound 4b", a trade name, a typo — and formulae do not.
  This only ever *adds* a stream.
- **Nothing is dropped.** A substance matching no pattern goes to Named Waste
  *and* onto the review list by name. An unlabelled bottle is exactly the
  failure this form exists to prevent.
- Any H400–H413 code adds Named Waste with the reason that nothing containing
  it, including the rinsings, goes down the sink.

## Where this is deliberately more cautious than autocoshh

[`aymannel/autocoshh`](https://github.com/aymannel/autocoshh) (MIT) fills the
same form and was read for this table — its `autocoshh.db` confirmed the
eleven control options and their order, and the shape of code → route/control
mapping is its idea. Credit where it is due. Five rules here differ on purpose:

| code(s) | autocoshh | here | reason |
|---|---|---|---|
| `H224`–`H227` flammable liquids | Skin only | Skin **and Inhalation** | the statement says "liquid **and vapour**": there is vapour above it at room temperature, so inhalation is live whether or not a separate H336 is on the label |
| `H300`–`H303` acute oral | no glove | **Gloves** | nobody drinks the reagent; it is swallowed off a contaminated hand, so the glove is what interrupts the route |
| `H318`–`H320` eye codes | no glove | **Gloves** | the splash that reaches an eye came off a hand or a pipette; the glove is cheap and the eye is not |
| `H350`, `H351` carcinogens | no pregnancy restriction | **Not to be used if pregnant** | this teaching lab restricts the whole CMR set, not only reproductive toxins; the cost is a conversation |
| `H230`, `H231` | ticks "Do not expose to air" | **does not** | the code says it reacts explosively *in the absence of air*; ticking air exclusion would tell the reader a false control works |

Also added here and not in that mapping: the EUH statements (`EUH014`, `EUH029`,
`EUH031`, `EUH032`, `EUH018`, `EUH019`, `EUH044`, `EUH066`, `EUH071`), which for
several reagents are the only warning about gas evolution or peroxide formation
that a form would otherwise get; the malodour list; the waste mapping; and the
unknown-code fallback.

## What this will not do

- It will not invent a hazard code. Only codes returned by a named classifier
  get onto the form, and the source is carried with them.
- It will not fill in "Approved By" or the date. A competent person signs.
- It will not decide scale or containment. `Special measures:` stays empty.
- It will not tick "no" on a risk row by default — every row comes back with a
  sentence saying either what argued for it or that nothing did.

## Running the rules on their own

```bash
python -m unittest discover -s tests      # offline; no network, no template
```

`tests/test_rules.py` names one representative code per hazard class and
asserts the route and control that class exists to produce, then checks the
behaviour that keeps the form honest: unknown codes, combined codes,
subdivision letters, unrecognised waste, and a substance PubChem has never
heard of.
