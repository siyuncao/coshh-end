"""
From a typed list of substances to a COSHH assessment, with no model involved.

`coshh.manual` exists because reading a *procedure* is a language job: prose
names things it does not use, defines its own abbreviations, and hides the
quantities inside sentences. A **list** is not prose. Somebody who writes

    pyrrolidine 7.11 g
    triethylamine, 15 mL
    3 M HNO3 20 mL
    TEMPO 26.8 g (CAS 2564-83-2)

has already done the reading. What is left is splitting a name from an amount,
and that is a job for a regular expression and a few honest rules — no API key,
no network call to anybody but PubChem, no cost, and the same answer every time.

So this module is the default path through the app, and `coshh.manual` is the
option for people who have a key and would rather paste the whole method.

Everything downstream is shared, not copied. `read_list` returns exactly the
shape `manual.extract` returns, so `assess` here is `manual.assess` with the
model swapped out for the parser: the same dedupe, the same PubChem lookup, the
same rule table, the same review list, the same dict the form writer consumes.

What this module refuses to do:

* **Drop a line.** A line it cannot split becomes a substance whose amount is
  blank, plus a line in `review` saying which line it was and that nobody read
  it. Silence is the one outcome that is never correct here: a reagent missing
  from a COSHH form is a reagent nobody assessed.
* **Fold text into a name quietly.** `sodium borohydride 1.2 g in 10 mL MeOH`
  is one line naming two substances. Rejoining it into one row is still the
  best reading of the text, but the leftover words earn a line in `review`
  asking for the second substance on its own line — otherwise the methanol is
  in nobody's row and nothing anywhere says so.
* **Convert anything.** `7.11 g` reaches the form as `7.11 g`. Ranges, `~`,
  `2 x 20 mL` and µL all survive character for character; this is the field a
  chemist reads back off the paper and compares with the balance.
* **Guess chemistry.** It splits text. Every hazard on the finished form still
  comes from PubChem's GHS labelling by way of `coshh.rules`.
* **Guess a concentration into an amount.** In `3 M HNO3 20 mL` the `3 M`
  belongs to the substance's name and the `20 mL` is how much there is. Molarity
  and per-cent are deliberately not amount units, which is what keeps
  `0.5 M NaOH` from being read as half a mole of hydroxide.

The text is data, not instructions — but that is nearly free here, because
nothing in this module can be instructed. There is no model to talk to.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

from coshh import manual

__all__ = ["parse_line", "parse_list", "read_list", "assess", "notes_for",
           "no_amount_note", "is_no_amount_note",
           "ListTooLong", "NothingToList", "NO_MODEL"]


#: What goes in the assessment's `model` field. The form writer does not read
#: it; a person reading the JSON should still be told that nothing read this but
#: a regular expression.
NO_MODEL = "none - substance list parsed locally, no model call"

#: A list is one experiment's reagents, not a stockroom inventory. The guard is
#: generous enough that nobody hits it by accident and small enough that a
#: pasted catalogue is refused rather than turned into 900 PubChem lookups.
MAX_LIST_CHARS = 20_000
MAX_LIST_LINES = 200


class ListTooLong(ValueError):
    """More lines than one experiment has reagents."""


class NothingToList(ValueError):
    """The box was empty, or held nothing with a letter or a digit in it."""


# --------------------------------------------------------------------------
# What an amount looks like
#
# Deliberately *not* here: M, mM, N, %, w/w, v/v, ppm, molar. Those describe
# what the bottle contains, not how much of it is being used, and a form that
# records "0.5 M" in the Amount cell has lost the information it exists to hold.
# --------------------------------------------------------------------------

#: Mass, volume and countable things — the amounts a form actually wants.
_SIZE_UNITS = (
    "mg", "g", "kg", "ng", "µg", "μg", "ug", "mcg",
    "mL", "ml", "L", "l", "cL", "cl", "dL", "dl", "µL", "μL", "uL", "ul",
    "cm3", "cm³", "dm3", "dm³", "cc",
    "drop", "drops", "pellet", "pellets", "spatula", "spatulas",
    "crystal", "crystals", "piece", "pieces", "scoop", "scoops",
    "tablet", "tablets", "sheet", "sheets", "vial", "vials",
)

#: Amounts in moles or equivalents. Real amounts, but a chemist writing
#: "toluene 5 mL (0.047 mol)" means the 5 mL, so these lose the tie-break.
_MOLE_UNITS = (
    "mmol", "mol", "moles", "µmol", "μmol", "umol", "nmol",
    "equiv", "equivalents", "equivs", "eq",
)


def _alternation(*groups: Any) -> str:
    """Units as a regex alternation, longest first so `mg` beats `g`."""
    words = {word for group in groups for word in group}
    return "|".join(re.escape(word) for word in sorted(words, key=lambda w: (-len(w), w)))


_NUMBER = r"\d+(?:[.,]\d+)?"
#: `5-10`, `5 to 10`, `5`. The separator set is the one people actually type,
#: including both dashes a word processor produces.
_SPAN = r"{n}(?:\s*(?:[-–—]|\bto\b|±)\s*{n})?".format(n=_NUMBER)
_QUALIFIER = r"(?:[~≈<>≤≥]|ca\.?|approx\.?|about)?\s*"
#: `2 x 20 mL` — two portions of twenty, which is not the same as 40 mL and is
#: not this tool's to add up.
_MULTIPLIER = r"(?:{n}\s*[x×]\s*)?".format(n=_NUMBER)

_AMOUNT_RE = re.compile(
    r"(?<![A-Za-z0-9.])"                       # not mid-number, not mid-formula
    r"{qual}{mult}{span}\s*"
    r"(?P<unit>{units})"
    r"(?![A-Za-z])"                            # `5 g` yes, `5 gram-ish` no
    r"(?!\s*/)".format(                        # `0.5 mol/L` is a concentration
        qual=_QUALIFIER, mult=_MULTIPLIER, span=_SPAN,
        units=_alternation(_SIZE_UNITS, _MOLE_UNITS)),
    re.IGNORECASE)

_SIZE_LOWER = {unit.lower() for unit in _SIZE_UNITS}

#: `CAS 2564-83-2`, `CAS No. 64-17-5`, or a bare `2564-83-2`.
_CAS_RE = re.compile(
    r"(?:\bcas(?:\s*(?:no\.?|number|nr\.?|rn|#))?\s*[:.]?\s*)?"
    r"\b(?P<cas>\d{2,7}-\d{2}-\d)\b",
    re.IGNORECASE)

#: `1.`, `2)`, `-`, `*`, `•`. The trailing space is required, which is what
#: stops `3 M HNO3` losing its concentration to a list-numbering rule.
_BULLET_RE = re.compile(r"^\s*(?:[-*•·‣▪>+–—]|\(?\d{1,2}[.)])\s+")

_EMPTY_BRACKETS_RE = re.compile(r"\(\s*[,;]?\s*\)|\[\s*[,;]?\s*\]")
_LEADING_JUNK_RE = re.compile(r"^[\s,;:|/–—\-)\]}]+")
_TRAILING_JUNK_RE = re.compile(r"[\s,;:|/–—\-([{]+$")
_LEADING_OF_RE = re.compile(r"^(?:of|de|des)\s+", re.IGNORECASE)
#: A bracketed aside, for the lookup name: `dichloromethane (anhydrous)` is one
#: substance PubChem knows and one search term it does not.
_BRACKETS_RE = re.compile(r"\s*[(\[][^()\[\]]*[)\]]")

#: Words and figures that describe the bottle rather than the molecule.
#: `coshh.manual` asks the model for exactly this ("concentrated nitric acid" ->
#: "nitric acid") so that PubChem is searched for something it has heard of. The
#: list is closed and boring on purpose: it strips grade, strength and state,
#: and it is never allowed to strip its way to a *different* substance.
_QUALIFIER = (
    r"\d+(?:[.,]\d+)?\s*(?:M|mM|N|%|w/w|v/v|wt\s*%)|"
    r"concentrated|conc\.?|dilute|dil\.?|saturated|sat\.?[dn]?|aqueous|aq\.?|"
    r"anhydrous|dry|dried|absolute|abs\.?|glacial|fuming|technical|reagent[- ]grade|"
    r"freshly\s+distilled|distilled|degassed|solid|powdered|granular|"
    r"\d+(?:[.,]\d+)?\s*%"
)
#: `\b` would be wrong here: half these alternatives end in `%` or `.`, and a
#: word boundary after a non-word character demands a word character next, so
#: `95%` at the end of a fragment matched nothing at all. What is meant is
#: "the qualifier is not the front of a longer word" — `dry` but not `dryer`.
_ENDS_QUALIFIER = r"(?![A-Za-z0-9])"
_QUALIFIER_RE = re.compile(
    r"^(?:" + _QUALIFIER + r")" + _ENDS_QUALIFIER + r"[\s,.:-]*", re.IGNORECASE)
#: The same list, but the fragment has to be *nothing but* a qualifier.
_QUALIFIER_ONLY_RE = re.compile(
    r"^(?:" + _QUALIFIER + r")[\s,.:-]*$", re.IGNORECASE)

#: Words that are only a substance in company. Strip "dry" off "dry ice" and the
#: search term becomes "ice", which PubChem answers with water — a different
#: molecule, a different form, and nobody the wiser. So the stripping stops here.
_ONLY_IN_COMBINATION = frozenset({"ice", "acid", "base", "solution", "gas", "powder"})

#: What a bottle contains, written out: "60% dispersion in mineral oil",
#: "solution in water". Only ever matched against a *trailing* comma fragment.
_DISPERSION_RE = re.compile(
    r"^(?:dispersion|solution|suspension|slurry|emulsion)\s+in\s+\S", re.IGNORECASE)


def _is_qualifier_only(fragment: str) -> bool:
    """True when a fragment describes the bottle and names nothing new.

    `95%`, `2 M`, `anhydrous`, `60% dispersion in mineral oil`. Used on the last
    comma-separated piece of a name and nowhere else, so the worst it can do is
    shorten a search term — the row's own label keeps every word that was typed.
    """
    plain = _tidy(fragment)
    while plain:
        if _QUALIFIER_ONLY_RE.match(plain):
            return True
        stripped = _tidy(_QUALIFIER_RE.sub("", plain))
        if stripped == plain:
            break
        plain = stripped
    return not plain or bool(_DISPERSION_RE.match(plain))


def _drop_trailing_qualifiers(plain: str) -> str:
    """`sodium borohydride, 95%` -> `sodium borohydride`.

    "name, grade, amount" is one of the commonest ways a reagent list is
    written, and the bracketed form of the same thing — `sodium hydride (60%
    dispersion in mineral oil)` — already resolved, so leaving the comma form to
    search PubChem for "sodium borohydride, 95%" (which resolves to nothing) was
    both lossy and inconsistent. The first fragment is never dropped: it is the
    only part guaranteed to be the substance.
    """
    if "," not in plain:
        return plain
    parts = plain.split(",")
    kept = len(parts)
    while kept > 1 and _is_qualifier_only(parts[kept - 1]):
        shorter = _tidy(",".join(parts[:kept - 1]))
        if not shorter or shorter.lower() in _ONLY_IN_COMBINATION:
            break                               # "acid" is not a substance
        kept -= 1
    if kept == len(parts):
        # `N,N-dimethylformamide` and `1,3-propanediol` come back character for
        # character: the pieces are rejoined on the comma they were split on.
        return plain
    return _tidy(",".join(parts[:kept]))


def _search_name(name: str) -> str:
    """The plain chemical name to search PubChem for, or "" if it is already it."""
    plain = _drop_trailing_qualifiers(_tidy(_BRACKETS_RE.sub(" ", name)))
    while True:
        stripped = _tidy(_QUALIFIER_RE.sub("", plain))
        if stripped == plain or not stripped:
            break
        if stripped.lower() in _ONLY_IN_COMBINATION:
            break
        plain = stripped
    if not plain or plain.lower() == name.lower():
        return ""
    return plain


def _tidy(text: str) -> str:
    """Whitespace, orphaned brackets and dangling punctuation off a fragment."""
    text = _EMPTY_BRACKETS_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = _LEADING_JUNK_RE.sub("", text)
    text = _TRAILING_JUNK_RE.sub("", text)
    return text.strip()


def _valid_cas(number: str) -> bool:
    """The CAS check digit: sum of the digits weighted by position, mod 10.

    Worth the six lines. Without it, `1,3-propanediol 5-10 g` or a date in a
    note becomes a CAS number, and a wrong CAS number on a COSHH form sends
    whoever checks it to the wrong safety data sheet — which is worse than no
    number at all.
    """
    digits = number.replace("-", "")
    if not digits.isdigit():
        return False
    body, check = digits[:-1], int(digits[-1])
    total = sum((i + 1) * int(d) for i, d in enumerate(reversed(body)))
    return total % 10 == check


def _take_cas(text: str) -> tuple:
    """(text without the CAS number, the CAS number, any note about it)."""
    for match in _CAS_RE.finditer(text):
        number = match.group("cas")
        labelled = match.group(0).lower().startswith("cas")
        if not labelled and not _valid_cas(number):
            continue                            # a range or a date, not a CAS number
        note = ""
        if not _valid_cas(number):
            note = ("the CAS number {!r} does not pass its own check digit, so it has been "
                    "kept but not trusted - check it against the bottle".format(number))
        return text[:match.start()] + " " + text[match.end():], number, note
    return text, "", ""


def _extend(work: str, matches: List[Any], primary: Any) -> int:
    """Where the amount ends, once a bracketed restatement is swallowed.

    `toluene 5 mL (0.047 mol)` is one amount written twice, not an amount and a
    name. Anything separated from the amount by nothing but punctuation joins it.
    """
    end = primary.end()
    for match in matches:
        if match.start() < end:
            continue
        if re.fullmatch(r"[\s(,;=/·×xX–—-]*", work[end:match.start()]):
            end = match.end()
        else:
            break
    span = work[primary.start():end]
    if span.count("(") > span.count(")") and work[end:end + 1] == ")":
        end += 1
    return end


def parse_line(line: str) -> Optional[Dict[str, Any]]:
    """
    One typed line into one substance, in the shape `coshh.manual` produces.

    Returns `None` only for a line with no letter and no digit in it — a blank,
    a rule of dashes, a stray comma. Everything else comes back as a substance,
    because the alternative is a reagent that quietly never reached the form.
    A line that could not be split keeps its whole text as the name, an empty
    amount, and a `parse_note` saying so.
    """
    raw = line.strip()
    if not re.search(r"[A-Za-z0-9]", raw):
        return None

    work = _BULLET_RE.sub("", raw)
    work = work.replace(" ", " ")
    work, cas, note = _take_cas(work)

    matches = list(_AMOUNT_RE.finditer(work))
    primary = None
    for match in matches:
        if match.group("unit").lower() in _SIZE_LOWER:
            primary = match
            break
    if primary is None and matches:
        primary = matches[0]

    amount = ""
    remark = ""                 # a short aside a comma split off, for the tag
    head = ""                   # the pre-amount text, when the tail was glued on
    if primary is None:
        name = _tidy(work)
    else:
        end = _extend(work, matches, primary)
        amount = re.sub(r"\s+", " ", work[primary.start():end]).strip()
        before, after = _tidy(work[:primary.start()]), _tidy(work[end:])
        if before and after:
            # `ethanol 30 mL, dried over MgSO4` — what follows the amount behind
            # a comma or a bracket is a remark about the substance, not more of
            # its name. Anything else is two halves of one name, rejoined.
            tail = work[end:].lstrip()
            if tail[:1] in (",", ";", "(", "[", "-", "–", "—"):
                name, remark = before, after
                note = "; ".join(p for p in (note, (
                    "the line's remark {!r} was kept as a note and not assessed - if it "
                    "names another substance, give it its own line so it gets its own "
                    "row".format(after))) if p)
            else:
                # `sodium borohydride 1.2 g in 10 mL MeOH` is one row and two
                # substances, and the methanol is in nobody's row. Rejoining is
                # still the best reading of the text, but it is never silent:
                # the fold is said out loud, and PubChem is searched for the
                # half of the line that came before the amount.
                name = _tidy(before + " " + after)
                head = before
                note = "; ".join(p for p in (note, (
                    "the text after the amount ({!r}) was read as part of the name; if "
                    "this line names a second substance, put it on its own line so it "
                    "gets its own row".format(after))) if p)
        elif before:
            name = before
        else:
            name = _tidy(_LEADING_OF_RE.sub("", after))

    if not name:
        if cas:
            # `CAS 64-17-5, 500 mL` names the substance, just not in words, and
            # PubChem answers a CAS number first. Throwing the amount away here
            # put "500 mL" in the Name cell and left Amount — the column read
            # back against the balance — blank.
            name = "CAS " + cas
            note = "; ".join(p for p in (
                note, "identified by CAS number only - write the substance's name in") if p)
        else:
            # The line was an amount and nothing else. It is still not deleted.
            name = raw
            amount = ""
            note = "; ".join(p for p in
                             (note, "no substance name could be read from this line") if p)

    # `dichloromethane (anhydrous)` is the row's label and `dichloromethane` is
    # the search term. `manual.assess` reports the difference and falls back to
    # the label if the search term finds nothing, so neither is lost.
    lookup_name = _search_name(name)
    if head:
        # The glued-on tail is not part of any substance's name, and leaving it
        # in the search term costs the row its classification outright.
        lookup_name = _search_name(head) or head

    return {
        "name": name,
        "lookup_name": lookup_name,
        "cas": cas,
        "formula": "",
        "amount": amount,
        # Only what the line itself said. Nothing here decides that something is
        # a solvent or a catalyst.
        "role": remark if remark and primary is not None and amount else "",
        "used": True,
        # The line as typed, which is what the review page quotes back.
        "source_line": raw,
        "raw": raw,
        "parse_note": note,
    }


def parse_list(text: str) -> List[Dict[str, Any]]:
    """Every line of the box as a substance, in order, nothing dropped."""
    if not (text or "").strip():
        raise NothingToList(
            "there is nothing in the substance list. Type one substance per line, "
            "with how much of it you are using: 'pyrrolidine 7.11 g'.")
    if len(text) > MAX_LIST_CHARS:
        raise ListTooLong(
            "{:,} characters is more than one experiment's reagents. Nothing here is "
            "truncated, so list the substances for the experiment you are assessing.".format(
                len(text)))
    lines = text.splitlines()
    if len(lines) > MAX_LIST_LINES:
        raise ListTooLong(
            "{:,} lines is more than one experiment's reagents. Nothing here is truncated, "
            "so list the substances for the experiment you are assessing.".format(len(lines)))

    out = [entry for entry in (parse_line(line) for line in lines) if entry]
    if not out:
        raise NothingToList(
            "no substance could be read from that. Type one substance per line, with how "
            "much of it you are using: 'pyrrolidine 7.11 g'.")
    return out


#: What a row with no amount earns in the review. It is a named shape rather
#: than an inline string because `app.corrected` has to recognise it again: once
#: the chemist has typed the amount in, this line sits in the document arguing
#: with the cell beside it, and a review block that contradicts the form is how
#: a signer learns to stop reading review blocks.
_NO_AMOUNT_NOTE = ("{name}: no amount was read from the line {raw!r}, so the Amount cell is "
                   "blank. Write in how much you are using before this form is signed.")
_NO_AMOUNT_MARK = "no amount was read from the line"


def no_amount_note(name: str, raw: str) -> str:
    """The review line for a row whose Amount cell came out blank."""
    return _NO_AMOUNT_NOTE.format(name=name, raw=raw)


def is_no_amount_note(line: str, raw: str) -> bool:
    """True when `line` is :func:`no_amount_note` for the typed line `raw`."""
    return bool(raw) and _NO_AMOUNT_MARK in line and repr(raw) in line


def notes_for(entries: List[Dict[str, Any]]) -> List[str]:
    """The review lines a parsed list earns, before PubChem is asked anything."""
    notes: List[str] = []
    for entry in entries:
        if entry["parse_note"] and not entry["amount"]:
            notes.append(
                "{!r} could not be read as a substance and an amount ({}). It is on the form "
                "with a blank Amount rather than left off it - correct the name and write in "
                "how much you are using.".format(entry["raw"], entry["parse_note"]))
        elif entry["parse_note"]:
            notes.append("{}: {}.".format(entry["name"], entry["parse_note"]))
        elif not entry["amount"]:
            notes.append(no_amount_note(entry["name"], entry["raw"]))
    return notes


def read_list(text: str) -> Dict[str, Any]:
    """
    The substance list in the shape `manual.extract` returns, plus its notes.

    No scheme and no equipment: a list of reagents says nothing about the
    reaction, and `manual.assess` prints its own "draw the scheme in by hand"
    into that box when the scheme is empty, which is the honest answer.
    """
    entries = parse_list(text)
    return {"scheme": "", "substances": entries, "equipment": [],
            "notes": notes_for(entries)}


def assess(text: str, *, title: str = "", name: str = "", date: str = "",
           college: str = "", year: str = "",
           lookup: Optional[Callable[[str, str], Dict[str, Any]]] = None,
           ) -> Dict[str, Any]:
    """
    A typed substance list in, a filled-in COSHH assessment out (no Word yet).

    The sibling of `manual.assess`, and literally so: the list is parsed here and
    everything after that — dedupe, PubChem, the rule table, the review list, the
    dict the writer consumes — is `manual.assess` doing its usual work with the
    parser handed to it in place of the model. `lookup` is injectable so the whole
    path can be tested offline; the default is `safety.hazards`.
    """
    notes: List[str] = []

    def extractor(procedure: str, **_ignored: Any) -> Dict[str, Any]:
        read = read_list(procedure)
        notes.extend(read["notes"])
        return read

    assessment = manual.assess(
        text, title=title, name=name, date=date, college=college, year=year,
        model=NO_MODEL, extractor=extractor, lookup=lookup)

    # The parser's complaints belong at the top: a blank amount is something the
    # reader fixes before they read a word about hazards.
    assessment["review"] = list(dict.fromkeys(notes + list(assessment["review"])))
    assessment["needs_review"] = bool(assessment["review"]) or any(
        row["needs_review"] for row in assessment["substances"])
    return assessment
