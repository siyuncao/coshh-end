"""
A small web app around the COSHH drafting pipeline.

Three routes, and a deliberate gap between the second and the third:

    GET  /           paste a lab manual, fill in the header, press the button
    POST /draft      read it, show every substance and every tick it proposes,
                     with anything unclassified shouted at the top, and let the
                     chemist correct all of it
    POST /document   turn *the corrected draft* into the .docx and hand it back

The gap is the safety argument. `coshh.manual` reads a procedure with a language
model and looks each substance up in PubChem; both of those can be wrong, and a
COSHH form is a document somebody signs. So the tool never goes from text to
Word in one step. It shows its work, a human corrects it, and only then is there
a file. `Approved By` is left blank by the writer and cannot be filled in here.

Nothing is written to disk. The generated document is built in a temporary file,
read into memory, and the temporary file is deleted before the response is sent;
the pasted manual is never saved at all.

Run it::

    .venv/bin/uvicorn app:app --reload --port 8000
"""

from __future__ import annotations

import html
import io
import json
import os
import tempfile
import unicodedata
from urllib.parse import quote
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response

from coshh import docx_form, manual, rules

app = FastAPI(title="COSHH draft", docs_url=None, redoc_url=None)

#: The chemist's own template. `coshh/docx_form.py` ships the default path;
#: point `COSHH_TEMPLATE` somewhere else to use a different form. The template
#: itself is never committed — see the README.
TEMPLATE_PATH = os.environ.get("COSHH_TEMPLATE") or None

#: A paste box is not an upload endpoint; refuse anything absurd early.
MAX_UPLOAD_BYTES = 4 * 1024 * 1024

STANDING_NOTE = (
    "This is a draft. A competent person reads it, corrects it and signs it. "
    "Approved By and its date are left blank on purpose — this tool does not sign forms."
)

PRIVACY_NOTE = (
    "Nothing is stored. The manual you paste is held only for the length of the "
    "request, and the document is built in a temporary file that is deleted "
    "before it reaches you."
)


# --------------------------------------------------------------------------
# Page furniture
# --------------------------------------------------------------------------

def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


CSS = """
:root {
  --paper: #fbfaf7; --ink: #1d1c19; --soft: #6b675d; --rule: #ddd8cb;
  --accent: #7a2e2e; --accent-soft: #f3e9e4;
  --warn: #9a5b12; --warn-bg: #fdf4e6; --warn-rule: #e3c48d;
  --ok: #3f6b45; --field: #ffffff;
}
@media (prefers-color-scheme: dark) {
  :root {
    --paper: #16151300; --paper: #161513; --ink: #eae6dc; --soft: #a19c8f; --rule: #37342d;
    --accent: #d99a94; --accent-soft: #2b2220;
    --warn: #e0ab5e; --warn-bg: #2a2117; --warn-rule: #5c4726;
    --ok: #8fb894; --field: #1f1e1b;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 1.5rem 1rem 5rem; background: var(--paper); color: var(--ink);
  font: 16px/1.6 ui-serif, Georgia, "Times New Roman", serif;
  -webkit-text-size-adjust: 100%;
}
main { max-width: 47rem; margin: 0 auto; }
h1 { font-size: 1.5rem; margin: 0 0 .2rem; letter-spacing: .01em; }
h2 {
  font-size: 1.05rem; margin: 2.2rem 0 .7rem; padding-bottom: .3rem;
  border-bottom: 1px solid var(--rule); font-weight: 600;
}
h3 { font-size: .98rem; margin: 0 0 .4rem; font-weight: 600; }
p { margin: .5rem 0; }
a { color: var(--accent); }
.sub { color: var(--soft); font-size: .9rem; margin: 0 0 1.4rem; }
.note {
  border-left: 3px solid var(--accent); background: var(--accent-soft);
  padding: .7rem .9rem; margin: 1rem 0; font-size: .9rem; border-radius: 0 3px 3px 0;
}
.alarm {
  border: 1px solid var(--warn-rule); background: var(--warn-bg); color: var(--ink);
  padding: .8rem 1rem; margin: 1.2rem 0; border-radius: 3px;
}
.alarm h3 { color: var(--warn); }
.alarm ul { margin: .4rem 0 0; padding-left: 1.1rem; }
.alarm li { margin: .3rem 0; font-size: .9rem; }
label { display: block; font-size: .85rem; color: var(--soft); margin-bottom: .2rem; }
input[type=text], input[type=date], textarea, select {
  width: 100%; padding: .5rem .6rem; background: var(--field); color: var(--ink);
  border: 1px solid var(--rule); border-radius: 3px; font: inherit; font-size: .95rem;
}
textarea { line-height: 1.5; resize: vertical; }
input:focus, textarea:focus, select:focus { outline: 2px solid var(--accent); outline-offset: -1px; }
.grid { display: grid; gap: .8rem; grid-template-columns: 1fr 1fr; }
.grid .wide { grid-column: 1 / -1; }
@media (max-width: 34rem) { .grid { grid-template-columns: 1fr; } }
.card {
  border: 1px solid var(--rule); border-radius: 4px; padding: .9rem 1rem;
  margin: .9rem 0; background: var(--field);
}
.card.unknown { border-color: var(--warn-rule); border-left-width: 4px; }
.card.equipment { border-left: 4px solid var(--soft); }
.tag {
  display: inline-block; font-size: .72rem; letter-spacing: .04em; text-transform: uppercase;
  padding: .1rem .4rem; border: 1px solid var(--rule); border-radius: 2px;
  color: var(--soft); margin-left: .4rem; vertical-align: 2px;
}
.tag.warn { color: var(--warn); border-color: var(--warn-rule); background: var(--warn-bg); }
.boxes { display: grid; gap: .25rem; margin: .3rem 0 0; }
.boxes label {
  display: flex; gap: .5rem; align-items: flex-start; font-size: .88rem;
  color: var(--ink); margin: 0; cursor: pointer;
}
.boxes input { margin: .35rem 0 0; flex: none; }
.why { color: var(--soft); font-size: .82rem; margin: .35rem 0 0; }
details { margin: .5rem 0 0; }
summary { cursor: pointer; font-size: .84rem; color: var(--soft); }
details .why { margin: .4rem 0 .2rem; }
.split { display: grid; gap: 1rem 1.4rem; grid-template-columns: 1fr 1fr; }
@media (max-width: 34rem) { .split { grid-template-columns: 1fr; } }
button {
  font: inherit; font-size: 1rem; padding: .65rem 1.4rem; border-radius: 3px;
  background: var(--accent); color: #fff; border: 1px solid var(--accent); cursor: pointer;
}
button:hover { filter: brightness(1.08); }
button.plain { background: transparent; color: var(--accent); }
.actions { display: flex; gap: .8rem; align-items: center; flex-wrap: wrap; margin-top: 1.6rem; }
footer { margin-top: 3rem; padding-top: .9rem; border-top: 1px solid var(--rule);
         color: var(--soft); font-size: .82rem; }
code { font-family: ui-monospace, Menlo, monospace; font-size: .85em; }
.quote { color: var(--soft); font-size: .85rem; font-style: italic; }
"""


def page(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>{title}</title><style>{css}</style></head>"
        "<body><main>{body}"
        "<footer>{standing}<br>{privacy}</footer>"
        "</main></body></html>"
    ).format(title=esc(title), css=CSS, body=body,
             standing=esc(STANDING_NOTE), privacy=esc(PRIVACY_NOTE))


def error_page(heading: str, detail: str, back: bool = True) -> HTMLResponse:
    body = "<h1>{}</h1><div class=\"alarm\"><p>{}</p></div>".format(esc(heading), esc(detail))
    if back:
        body += "<p><a href=\"/\">Start again</a></p>"
    return HTMLResponse(page(heading, body), status_code=400)


# --------------------------------------------------------------------------
# GET /  -- paste the manual
# --------------------------------------------------------------------------

HEADER_FIELDS: Tuple[Tuple[str, str, str], ...] = (
    ("title", "Title of experiment", "text"),
    ("name", "Name", "text"),
    ("date", "Date", "text"),
    ("college", "College", "text"),
)


def header_inputs(values: Dict[str, str]) -> str:
    out = []
    for key, label, kind in HEADER_FIELDS:
        out.append(
            "<div><label for=\"{k}\">{l}</label>"
            "<input type=\"{t}\" id=\"{k}\" name=\"{k}\" value=\"{v}\"></div>".format(
                k=key, l=esc(label), t=kind, v=esc(values.get(key, ""))))
    year = values.get("year", "")
    options = "".join(
        "<option value=\"{v}\"{sel}>{lab}</option>".format(
            v=v, lab=esc(lab), sel=" selected" if year == v else "")
        for v, lab in (("", "—"), ("1", "Year 1"), ("2", "Year 2"), ("3", "Year 3")))
    out.append("<div><label for=\"year\">Year</label>"
               "<select id=\"year\" name=\"year\">{}</select></div>".format(options))
    return "<div class=\"grid\">{}</div>".format("".join(out))


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    body = """
<h1>COSHH draft</h1>
<p class="sub">Paste a lab manual. The tool reads the substances out of it, looks each one
up in PubChem, and proposes the ticks. You check every one of them before there is a document.</p>

<div class="note"><strong>{standing}</strong></div>

<form method="post" action="/draft" enctype="multipart/form-data">
  <h2>The form's own header</h2>
  <p class="sub">Copied onto the form exactly as you type them. Nothing here is guessed.</p>
  {header}

  <h2>The procedure</h2>
  <p class="sub">Paste the experimental section, or upload a <code>.txt</code> or
  <code>.docx</code>. Quantities are transcribed word for word, never converted.</p>
  <textarea name="manual" rows="14" placeholder="To a stirred solution of ..."></textarea>
  <p style="margin-top:.7rem"><label for="upload">or upload a file</label>
  <input type="file" id="upload" name="upload" accept=".txt,.docx,.md,text/plain"></p>

  <div class="actions">
    <button type="submit">Read the manual</button>
    <span class="sub" style="margin:0">One model call, then a PubChem lookup per substance.</span>
  </div>
</form>

<h2>What this does not do</h2>
<ul class="sub" style="padding-left:1.1rem">
  <li>It does not decide whether the scale or the containment is safe. That judgement is yours.</li>
  <li>It does not draw a reaction scheme; it writes the procedure's own description into that box.</li>
  <li>It does not invent hazard codes. If PubChem has no classification, the row says so loudly
      and you fill it in from the supplier's safety data sheet.</li>
  <li>It does not sign. <code>Approved By</code> stays blank.</li>
</ul>
""".format(standing=esc(STANDING_NOTE), header=header_inputs({}))
    return HTMLResponse(page("COSHH draft", body))


# --------------------------------------------------------------------------
# Reading the pasted manual
# --------------------------------------------------------------------------

def text_from_upload(filename: str, data: bytes) -> str:
    """Pull plain text out of an uploaded .docx, or decode anything else."""
    if filename.lower().endswith(".docx"):
        import docx  # python-docx, already a dependency of the writer

        document = docx.Document(io.BytesIO(data))
        parts: List[str] = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                parts.extend(cell.text for cell in row.cells)
        return "\n".join(part for part in parts if part.strip())
    return data.decode("utf-8", "replace")


# --------------------------------------------------------------------------
# POST /draft  -- show the reading, invite corrections
# --------------------------------------------------------------------------

def checkbox_group(field: str, options: Sequence[str], chosen: Sequence[str],
                   why: Optional[Dict[str, str]] = None) -> str:
    """A closed set of checkboxes. The form is exhaustive: unticked means unticked."""
    on = {str(c).strip().casefold() for c in chosen}
    why = why or {}
    rows = []
    for i, option in enumerate(options):
        checked = " checked" if option.strip().casefold() in on else ""
        reason = why.get(option, "")
        rows.append(
            "<label><input type=\"checkbox\" name=\"{f}\" value=\"{v}\"{c}>"
            "<span>{lab}{why}</span></label>".format(
                f=field, v=esc(option), c=checked, lab=esc(option),
                why="<span class=\"why\"> — {}</span>".format(esc(reason)) if reason else ""))
    return "<div class=\"boxes\">{}</div>".format("".join(rows))


def hazard_lines(row: Dict[str, Any]) -> str:
    """The Hazards cell as the writer would render it, one code per line."""
    lines = []
    for h in row.get("hazards") or ():
        if isinstance(h, dict):
            code = str(h.get("code", "")).strip()
            text = str(h.get("text", "")).strip()
            lines.append("{} - {}".format(code, text) if code and text else (code or text))
        else:
            lines.append(str(h))
    return "\n".join(lines)


def substance_card(i: int, row: Dict[str, Any]) -> str:
    equipment = row.get("kind") == "equipment"
    unknown = bool(row.get("unknown"))
    classes = "card" + (" unknown" if unknown else "") + (" equipment" if equipment else "")

    tags = []
    if equipment:
        tags.append("<span class=\"tag\">equipment</span>")
    if unknown:
        tags.append("<span class=\"tag warn\">no classification</span>")
    if row.get("role") and not equipment:
        tags.append("<span class=\"tag\">{}</span>".format(esc(row["role"])))

    source = ""
    if row.get("url"):
        source = ("<p class=\"why\">Classification from {src} — "
                  "<a href=\"{url}\" target=\"_blank\" rel=\"noreferrer\">PubChem entry</a></p>"
                  ).format(src=esc(row.get("source") or "PubChem"), url=esc(row["url"]))

    quote = ""
    if row.get("source_line"):
        quote = "<p class=\"quote\">Read from: “{}”</p>".format(esc(row["source_line"]))

    banner = ""
    if unknown:
        banner = ("<div class=\"alarm\"><h3>PubChem had no classification for this</h3>"
                  "<p style=\"font-size:.9rem;margin:.3rem 0 0\">The Hazards cell will carry "
                  "<code>{}</code> unless you type the codes in from the supplier's safety data "
                  "sheet. Typing them here replaces that banner with your text, and the draft "
                  "records that they came from you and not from PubChem.</p></div>"
                  ).format(esc(docx_form.UNASSESSED_TEXT))

    note = ""
    if row.get("note"):
        note = ("<p class=\"why\"><strong>Also written into the Hazards cell:</strong> {}</p>"
                ).format(esc(row["note"]))

    reasons = ""
    why_blocks = []
    for label, mapping in (("exposure routes", row.get("exposure_why")),
                           ("control measures", row.get("controls_why"))):
        if mapping:
            items = "".join("<p class=\"why\"><strong>{}</strong> — {}</p>".format(
                esc(k), esc(v)) for k, v in mapping.items())
            why_blocks.append("<p class=\"why\"><em>Why these {}:</em></p>{}".format(
                esc(label), items))
    if why_blocks:
        reasons = ("<details><summary>Why these boxes are ticked</summary>{}</details>"
                   ).format("".join(why_blocks))

    review = ""
    if row.get("review"):
        review = ("<div class=\"alarm\"><h3>Read before you sign</h3><ul>{}</ul></div>"
                  ).format("".join("<li>{}</li>".format(esc(line)) for line in row["review"]))

    return """
<div class="{classes}">
  <h3><label style="display:inline"><input type="checkbox" name="include_{i}" value="y" checked>
      include this row</label>{tags}</h3>
  {quote}
  {banner}
  <div class="grid" style="margin-top:.6rem">
    <div><label for="name_{i}">Substance or equipment</label>
      <input type="text" id="name_{i}" name="name_{i}" value="{name}"></div>
    <div><label for="amount_{i}">Mass / volume</label>
      <input type="text" id="amount_{i}" name="amount_{i}" value="{amount}"></div>
    <div class="wide"><label for="hazards_{i}">Hazards — one per line</label>
      <textarea id="hazards_{i}" name="hazards_{i}" rows="{rows}">{hazards}</textarea></div>
  </div>
  {note}
  {source}
  <div class="split" style="margin-top:.9rem">
    <div><h3>Exposure route</h3>{routes}</div>
    <div><h3>Control measures</h3>{controls}</div>
  </div>
  {reasons}
  {review}
</div>
""".format(
        classes=classes, i=i, tags="".join(tags), quote=quote, banner=banner, note=note,
        name=esc(row.get("name", "")), amount=esc(row.get("amount", "")),
        hazards=esc(hazard_lines(row)),
        rows=max(2, min(8, len(row.get("hazards") or ()) or 2)),
        source=source,
        routes=checkbox_group("route_{}".format(i), docx_form.EXPOSURE_ROUTES,
                              row.get("exposure") or ()),
        controls=checkbox_group("control_{}".format(i), docx_form.CONTROL_MEASURES,
                                row.get("controls") or ()),
        reasons=reasons, review=review)


def draft_body(assessment: Dict[str, Any], problem: str = "") -> str:
    rows = assessment.get("substances") or []
    implications = assessment.get("implications") or {}
    order = list(implications)

    alarms = []
    if problem:
        alarms.append("<div class=\"alarm\"><h3>Not yet</h3><p>{}</p></div>".format(esc(problem)))

    unknown = [r.get("name") or "<unnamed>" for r in rows if r.get("unknown")]
    if unknown:
        alarms.append(
            "<div class=\"alarm\"><h3>{n} substance{s} came back with no classification</h3>"
            "<ul>{items}</ul><p style=\"font-size:.9rem\">Each one is marked below. Fill the "
            "codes in from the supplier's safety data sheet, or leave the banner so whoever "
            "signs can see the gap.</p></div>".format(
                n=len(unknown), s="" if len(unknown) == 1 else "s",
                items="".join("<li>{}</li>".format(esc(u)) for u in unknown)))

    if assessment.get("review"):
        alarms.append(
            "<div class=\"alarm\"><h3>Check these before you sign</h3><ul>{}</ul></div>".format(
                "".join("<li>{}</li>".format(esc(line)) for line in assessment["review"])))

    skipped = assessment.get("mentioned_not_used") or []
    if skipped:
        alarms.append(
            "<div class=\"alarm\"><h3>Mentioned but read as not used</h3><ul>{}</ul>"
            "<p style=\"font-size:.9rem\">These have no row and nothing checked them for "
            "hazards. If you do handle them, go back and say so in the procedure.</p></div>".format(
                "".join("<li>{} <span class=\"quote\">{}</span></li>".format(
                    esc(s.get("name", "")), esc(s.get("source_line", "")))
                    for s in skipped)))

    risk_rows = []
    for idx, key in enumerate(order):
        value = implications[key] if isinstance(implications[key], dict) else {"yes": bool(implications[key])}
        why = value.get("why") or ""
        risk_rows.append("""
<div class="card">
  <h3><label style="display:inline"><input type="checkbox" name="risk_{idx}" value="y"{on}>
      {label}</label></h3>
  {why}
  <label for="prevention_{idx}" style="margin-top:.5rem">Prevention measures</label>
  <textarea id="prevention_{idx}" name="prevention_{idx}" rows="3">{prevention}</textarea>
</div>""".format(idx=idx, label=esc(key.rstrip(":")),
                 on=" checked" if value.get("yes") else "",
                 why="<p class=\"why\">{}</p>".format(esc(why)) if why else "",
                 prevention=esc(value.get("prevention") or "")))

    return """
<h1>Check the draft</h1>
<p class="sub">This is what was read out of the manual. Nothing has been written to a document
yet. Correct anything wrong here — every box below is the box that will be ticked.</p>

<div class="note"><strong>{standing}</strong></div>
{alarms}

<form method="post" action="/document">
  <input type="hidden" name="baseline" value="{baseline}">
  <input type="hidden" name="order" value="{order}">

  <h2>Header</h2>
  {header}

  <h2>Reaction scheme box</h2>
  <p class="sub">The tool writes words, not structures. Draw the scheme in by hand afterwards.</p>
  <textarea name="scheme_note" rows="4">{scheme}</textarea>

  <h2>Substances and equipment <span class="tag">{count} row{plural}</span></h2>
  {cards}

  <h2>Specific safety or risk implication</h2>
  {risks}

  <h2>Waste disposal</h2>
  {waste}
  <label for="waste_note" style="margin-top:.7rem">Waste note</label>
  <textarea id="waste_note" name="waste_note" rows="2">{waste_note}</textarea>

  <h2>Approved by</h2>
  <p class="sub">Left blank on purpose, and the writer refuses to save a form with anything in
  it. A competent person signs the printed form.</p>

  <div class="actions">
    <button type="submit">Generate the Word document</button>
    <a href="/" class="sub">Start again</a>
  </div>
</form>
""".format(
        standing=esc(STANDING_NOTE),
        alarms="".join(alarms),
        baseline=esc(json.dumps(assessment)),
        order=esc(json.dumps(order)),
        header=header_inputs({k: assessment.get(k, "") for k in
                              ("title", "name", "date", "college", "year")}),
        scheme=esc(assessment.get("scheme_note") or ""),
        count=len(rows), plural="" if len(rows) == 1 else "s",
        cards="".join(substance_card(i, r) for i, r in enumerate(rows)),
        risks="".join(risk_rows),
        waste=checkbox_group("waste", rules.WASTE_STREAMS, assessment.get("waste") or (),
                             assessment.get("waste_why")),
        waste_note=esc(assessment.get("waste_note") or ""))


@app.post("/draft", response_class=HTMLResponse)
async def draft(request: Request) -> HTMLResponse:
    form = await request.form()
    text = str(form.get("manual") or "")

    upload = form.get("upload")
    if upload is not None and getattr(upload, "filename", ""):
        data = await upload.read()
        if len(data) > MAX_UPLOAD_BYTES:
            return error_page("That file is too big",
                              "The upload is {:.1f} MB; the limit is {} MB.".format(
                                  len(data) / 1e6, MAX_UPLOAD_BYTES // (1024 * 1024)))
        try:
            uploaded = text_from_upload(upload.filename, data)
        except Exception as exc:  # a bad .docx is the user's problem, but say so plainly
            return error_page("That file could not be read",
                              "{}: {}".format(type(exc).__name__, exc))
        text = (text + "\n\n" + uploaded).strip() if text.strip() else uploaded

    if not text.strip():
        return error_page("Nothing to read",
                          "Paste the experimental procedure, or upload a .txt or .docx.")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return error_page(
            "No API key",
            "ANTHROPIC_API_KEY is not set in the environment this server is running in. "
            "Start it with the key loaded; see the README.")

    try:
        assessment = manual.assess(
            text,
            title=str(form.get("title") or ""), name=str(form.get("name") or ""),
            date=str(form.get("date") or ""), college=str(form.get("college") or ""),
            year=str(form.get("year") or ""))
    except manual.ManualTooLong as exc:
        return error_page("That procedure is too long", str(exc))
    except manual.ExtractionFailed as exc:
        return error_page("The manual could not be read", str(exc))
    except Exception as exc:
        return error_page("Something went wrong reading the manual",
                          "{}: {}".format(type(exc).__name__, exc))

    return HTMLResponse(page("Check the draft", draft_body(assessment)))


# --------------------------------------------------------------------------
# POST /document  -- the corrected draft becomes a .docx
# --------------------------------------------------------------------------

def corrected(baseline: Dict[str, Any], form: Any) -> Dict[str, Any]:
    """Fold the chemist's edits into the assessment the reader produced.

    The web form is authoritative for everything it shows. That matters most for
    the control measures: `fill_substance` is additive and the template arrives
    with spill / spectacles / lab coat already ticked, so an unticked box here
    has to be sent as an explicit `controls_off` or it would silently stay on.
    """
    out = dict(baseline)
    extra_review: List[str] = []

    for key in ("title", "name", "date", "college", "year"):
        out[key] = str(form.get(key) or "")
    out["scheme_note"] = str(form.get("scheme_note") or "")

    rows: List[Dict[str, Any]] = []
    for i, row in enumerate(baseline.get("substances") or []):
        if not form.get("include_{}".format(i)):
            extra_review.append(
                "{} was dropped from the form by hand; it is not assessed anywhere.".format(
                    row.get("name") or "a row"))
            continue
        new = dict(row)
        new["name"] = str(form.get("name_{}".format(i)) or "").strip()
        new["amount"] = str(form.get("amount_{}".format(i)) or "").strip()

        typed = [line.strip() for line in
                 str(form.get("hazards_{}".format(i)) or "").splitlines() if line.strip()]
        new["hazards"] = typed
        if not typed:
            # Clearing the box is not an answer. A blank Hazards cell reads as
            # "assessed, nothing to report" to whoever signs, which is the one
            # thing this tool exists to prevent, so it goes back through the
            # no-classification banner and is loud on both the page and the file.
            new["unknown"] = True
            extra_review.append(
                "{}: the hazards on this row were deleted by hand and nothing replaced them. "
                "The Hazards cell will carry the no-classification banner until you fill it "
                "in.".format(new["name"] or "a row"))
        if row.get("unknown") and typed:
            # The banner would contradict what the chemist just wrote, so it goes;
            # the provenance does not.
            new["unknown"] = False
            extra_review.append(
                "{}: the hazards on this row were typed in by hand, not found in PubChem. "
                "Check them against the supplier's safety data sheet.".format(
                    new["name"] or "a row"))

        chosen_routes = form.getlist("route_{}".format(i))
        chosen_controls = form.getlist("control_{}".format(i))
        new["exposure"] = list(chosen_routes)
        new["controls"] = list(chosen_controls)
        picked = {c.strip().casefold() for c in chosen_controls}
        new["controls_off"] = [c for c in docx_form.CONTROL_MEASURES
                               if c.strip().casefold() not in picked]
        rows.append(new)
    out["substances"] = rows

    try:
        order = json.loads(str(form.get("order") or "[]"))
    except ValueError:
        order = list(baseline.get("implications") or {})
    implications: Dict[str, Any] = {}
    for idx, key in enumerate(order):
        implications[key] = {
            "yes": bool(form.get("risk_{}".format(idx))),
            "prevention": str(form.get("prevention_{}".format(idx)) or "").strip(),
        }
    out["implications"] = implications

    out["waste"] = list(form.getlist("waste"))
    out["waste_note"] = str(form.get("waste_note") or "").strip()

    out["review"] = list(dict.fromkeys(list(baseline.get("review") or []) + extra_review))
    return out


def filename_for(assessment: Dict[str, Any]) -> Tuple[str, str]:
    """(an ASCII filename, the full one) for the Content-Disposition header.

    `ch.isalnum()` is true of Greek letters and of CJK, and Starlette encodes
    response headers as latin-1, so a title like "Delta-lactone synthesis"
    written with the actual Greek letter turned the whole download into a 500 —
    after the model call and every PubChem lookup had already been paid for, and
    on a POST the chemist cannot simply reload. Greek letters are ordinary in a
    chemistry title, so the stem is folded to ASCII for the plain `filename` and
    the real one is sent alongside it per RFC 5987.
    """
    stem = "".join(ch if (ch.isalnum() or ch in " -_") else "-"
                   for ch in (assessment.get("title") or "coshh")).strip()
    stem = "-".join(stem.split())[:60] or "coshh"
    ascii_stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode() or "coshh"
    return "COSHH-{}.docx".format(ascii_stem), "COSHH-{}.docx".format(stem)


@app.post("/document")
async def document(request: Request) -> Response:
    form = await request.form()
    try:
        baseline = json.loads(str(form.get("baseline") or ""))
    except ValueError:
        return error_page("The draft was lost",
                          "The hidden draft could not be read back. Start again.")
    if not isinstance(baseline, dict):
        return error_page("The draft was lost", "The hidden draft was not an assessment.")
    if not isinstance(baseline.get("substances") or [], list):
        return error_page("The draft was lost",
                          "The hidden draft's substance list was not a list of rows.")

    assessment = corrected(baseline, form)
    if not assessment["substances"]:
        return HTMLResponse(
            page("Check the draft",
                 draft_body(baseline,
                            problem="Every row was unticked, so there is nothing to assess. "
                                    "A COSHH form with no substances on it is not a COSHH form.")),
            status_code=400)

    # Built in a temporary file because python-docx writes to a path, read into
    # memory, and deleted before the response leaves. Nothing survives the request.
    handle, tmp = tempfile.mkstemp(suffix=".docx", prefix="coshh-")
    os.close(handle)
    try:
        docx_form.render(assessment, tmp, template_path=TEMPLATE_PATH)
        payload = Path(tmp).read_bytes()
    except FileNotFoundError:
        return error_page(
            "No template",
            "The COSHH template was not found at {}. Put your own .docx there, or set "
            "COSHH_TEMPLATE to its path — see the README.".format(
                TEMPLATE_PATH or docx_form.DEFAULT_TEMPLATE))
    except Exception as exc:
        return error_page("The document could not be written",
                          "{}: {}".format(type(exc).__name__, exc))
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass

    ascii_name, full_name = filename_for(assessment)
    disposition = "attachment; filename=\"{}\"".format(ascii_name)
    if full_name != ascii_name:
        disposition += "; filename*=UTF-8\'\'{}".format(quote(full_name, safe=""))
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": disposition, "Cache-Control": "no-store"},
    )
