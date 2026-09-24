"""
Hazard data for a compound, from PubChem.

A COSHH assessment (Control of Substances Hazardous to Health, the form a UK
lab fills in before anyone uses a substance) starts from the same handful of
facts every time: the pictograms, the signal word, the H numbers and the P
numbers. PubChem publishes them, free and without a key, so the tool can fill
that part in rather than making a chemist copy it off a supplier page.

What this is not: it is not the assessment. The assessment is the judgement
about *this* procedure, at *this* scale, in *this* fume hood, and that stays
with the chemist. This fetches the labelling and says where it came from.

Sources, in the order PubChem returns them, are kept and named. The first is
normally Regulation (EC) No 1272/2008, the harmonised classification that GB
CLP mirrors, which is the one a UK assessment should quote. Later blocks are
notified classifications, which disagree with each other often enough that
showing them without their source would be worse than not showing them.
"""

import re
import time
from typing import Optional

import httpx

BASE = "https://pubchem.ncbi.nlm.nih.gov/rest"
PAGE = "https://pubchem.ncbi.nlm.nih.gov/compound/{cid}#section=Safety-and-Hazards"
TIMEOUT = 15.0

# PubChem asks for no more than five requests a second and no key. One lookup
# per compound, cached for a week, is nowhere near that, and the data changes
# about as often as the regulation does.
CACHE_TTL = 7 * 24 * 3600
CACHE_MAX = 500
_cache: dict = {}


def _get(path: str, **params) -> Optional[dict]:
    """A GET that answers None rather than raising: no hazard data is not an error."""
    try:
        r = httpx.get(BASE + path, params=params, timeout=TIMEOUT,
                      headers={"User-Agent": "paper-to-order (chemical procurement)"})
    except Exception:
        return None
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def find_cid(name: str, cas: str = "") -> Optional[int]:
    """
    The PubChem compound id for a chemical, by CAS number first.

    A CAS number identifies one substance; a name can be a family, a trade
    name or a typo, so it is only the fallback.
    """
    for term in [t for t in (cas, name) if t and t.strip()]:
        data = _get(f"/pug/compound/name/{term.strip()}/cids/JSON")
        cids = (data or {}).get("IdentifierList", {}).get("CID") or []
        if cids:
            return int(cids[0])
    return None


def _strings(info: dict) -> list:
    return [s.get("String", "") for s in info.get("Value", {}).get("StringWithMarkup", [])]


def _markup(info: dict) -> list:
    return [m for s in info.get("Value", {}).get("StringWithMarkup", [])
            for m in s.get("Markup", [])]


def _pictograms(info: dict) -> list:
    """GHS03 and what it means, from the icon PubChem links to."""
    out = []
    for m in _markup(info):
        code = re.search(r"(GHS\d{2})", m.get("URL", "") or "")
        if code:
            out.append({"code": code.group(1), "meaning": m.get("Extra") or ""})
    return out


def _hazards(info: dict) -> list:
    """
    'H272 (91.7%): May intensify fire; oxidizer [Danger ...]' split into parts.

    The percentage is how many notifiers agreed, which belongs with the
    source rather than in the statement, and the bracket at the end repeats
    the signal word and the hazard class, so it is kept separately.
    """
    out = []
    for line in _strings(info):
        match = re.match(r"\s*(H\d{3}[A-Za-z]*)\s*(?:\(([\d.]+)%\))?\s*:\s*(.*)", line)
        if not match:
            continue
        code, share, rest = match.groups()
        klass = re.search(r"\[([^\]]+)\]\s*$", rest)
        out.append({
            "code": code,
            "text": re.sub(r"\s*\[[^\]]+\]\s*$", "", rest).strip(),
            "classification": klass.group(1).strip() if klass else None,
            "agreement": float(share) if share else None,
        })
    return out


def _precautions(info: dict) -> list:
    """The P numbers, in the order given, without the 'click each' sentence."""
    seen, out = set(), []
    for m in _markup(info):
        code = re.search(r"#(P\d{3}(?:\+P\d{3})*)", m.get("URL", "") or "")
        if code and code.group(1) not in seen:
            seen.add(code.group(1))
            out.append(code.group(1))
    if out:
        return out
    # Older records carry the codes in the text instead of as links.
    for line in _strings(info):
        for code in re.findall(r"P\d{3}(?:\s*\+\s*P\d{3})*", line):
            tidy = code.replace(" ", "")
            if tidy not in seen:
                seen.add(tidy)
                out.append(tidy)
    return out


def _sources(record: dict) -> dict:
    return {r.get("ReferenceNumber"): r.get("SourceName") or ""
            for r in record.get("Reference", [])}


def _section(record: dict) -> Optional[dict]:
    """The GHS Classification section, wherever PubChem has nested it."""
    stack = [record]
    while stack:
        node = stack.pop()
        for section in node.get("Section", []):
            if section.get("TOCHeading") == "GHS Classification":
                return section
            stack.append(section)
    return None


def classify(cid: int) -> Optional[dict]:
    """
    Every classification PubChem holds for a compound, grouped by who said it.

    None when PubChem has no GHS section at all, which is common for research
    compounds nobody has notified: silence is not "safe", and the caller says
    so rather than showing an empty form.
    """
    data = _get(f"/pug_view/data/compound/{cid}/JSON", heading="GHS Classification")
    record = (data or {}).get("Record")
    section = _section(record or {})
    if not section:
        return None

    names = _sources(record)
    blocks, order = {}, []
    for info in section.get("Information", []):
        ref = info.get("ReferenceNumber")
        if ref not in blocks:
            blocks[ref] = {"source": names.get(ref, ""), "pictograms": [],
                           "signal_word": None, "hazards": [], "precautions": [],
                           "note": None}
            order.append(ref)
        block, field = blocks[ref], info.get("Name")
        if field == "Pictogram(s)":
            block["pictograms"] = _pictograms(info)
        elif field == "Signal":
            block["signal_word"] = (_strings(info) or [None])[0]
        elif field == "GHS Hazard Statements":
            block["hazards"] = _hazards(info)
        elif field == "Precautionary Statement Codes":
            block["precautions"] = _precautions(info)
        elif field == "Note":
            block["note"] = (_strings(info) or [None])[0]

    classifications = [blocks[r] for r in order if blocks[r]["hazards"] or blocks[r]["pictograms"]]
    if not classifications:
        return None
    return {"cid": cid, "url": PAGE.format(cid=cid), "classifications": classifications}


def hazards(name: str, cas: str = "") -> dict:
    """
    What a COSHH assessment needs about one chemical, with its source.

    Always answers. `found` is False when PubChem does not know the compound
    or holds no classification for it, and `primary` is the block to quote:
    the harmonised EU classification when there is one, which is what GB CLP
    follows, and otherwise the first source PubChem lists.
    """
    key = (name.strip().lower(), cas.strip())
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_TTL:
        return hit[1]

    cid = find_cid(name, cas)
    data = classify(cid) if cid else None
    if not data:
        answer = {"found": False, "cid": cid, "name": name, "cas": cas,
                  "url": PAGE.format(cid=cid) if cid else None,
                  "primary": None, "other_sources": [],
                  "note": "PubChem holds no GHS classification for this one. "
                          "Use the supplier's safety data sheet."}
    else:
        blocks = data["classifications"]
        harmonised = next(
            (b for b in blocks if "1272/2008" in (b["source"] or "")), blocks[0])
        answer = {
            "found": True, "cid": data["cid"], "name": name, "cas": cas,
            "url": data["url"], "primary": harmonised,
            "other_sources": [b for b in blocks if b is not harmonised],
            "note": None,
        }

    if len(_cache) >= CACHE_MAX:
        _cache.clear()
    _cache[key] = (time.monotonic(), answer)
    return answer
