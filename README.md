# coshh-end

A lab manual goes in; a filled-in COSHH form comes out as a Word document,
on your own template, for a competent person to check and sign.

**COSHH** (Control of Substances Hazardous to Health) is the assessment a UK
lab fills in before anyone uses a substance. Every one of them starts from
the same handful of facts: the pictograms, the signal word, the H numbers and
the P numbers. This fetches that part from PubChem, free and without an API
key, works out which of the form's boxes those codes argue for, and writes
them into your template.

It is not the assessment. Scale, containment, spill and waste are judgements
about one procedure in one fume hood, and they stay with the chemist.
`Approved By` is left blank, and the writer refuses to save a form with
anything in it.

## The app

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export ANTHROPIC_API_KEY=...          # reading the manual needs a model
.venv/bin/uvicorn app:app --port 8000
```

Then open <http://127.0.0.1:8000>.

Three pages, and the gap between the second and the third is the point:

| | |
|---|---|
| `GET /` | Paste the experimental procedure, or upload a `.txt` / `.docx`, and fill in Title, Name, Date, College, Year. |
| `POST /draft` | Shows what was read: every substance, its amount transcribed word for word, its H-codes with the source named and linked, and every box that will be ticked, with anything PubChem could not classify shouted at the top. **Everything on this page is editable.** |
| `POST /document` | Turns *the corrected draft* into the .docx and hands it back as a download. |

The tool never goes from pasted text to Word in one step. A language model
reads the procedure and PubChem answers the lookups; both can be wrong, and a
COSHH form is a document somebody signs. So it shows its work, you correct it,
and only then is there a file.

Nothing is persisted. The manual you paste is held for the length of the
request; the document is built in a temporary file, read into memory, and the
file is unlinked before the response is sent.

### Supply your own template

The form is an Oxford *COSHH Form, Chemistry Teaching Laboratory* .docx, and
**no template is committed to this repo** — it is your document, and this repo
is public. Put yours at:

```
templates/coshh-template.docx
```

which `.gitignore` excludes, or point `COSHH_TEMPLATE` at it:

```bash
COSHH_TEMPLATE=~/my-coshh-form.docx .venv/bin/uvicorn app:app --port 8000
```

The writer addresses the template by table and cell position, and ticks the
checkboxes that are already in it, so a template with the same five-column
substance table, the same eleven Control Measures options and the same risk and
waste rows will work. A different form will not; see `docs/template-anatomy.md`
for exactly what is assumed.

## The parts, separately

Each layer is usable and arguable on its own, which is the point: a form
somebody signs should be defensible line by line.

```python
from safety import hazards

h = hazards("potassium permanganate", "7722-64-7")
h["primary"]["signal_word"]                      # 'Danger'
[p["code"] for p in h["primary"]["pictograms"]]  # ['GHS03', 'GHS07', 'GHS08', 'GHS09']
[x["code"] for x in h["primary"]["hazards"]]     # ['H272', 'H302', 'H361d', 'H400', 'H410']
h["primary"]["precautions"][:3]                  # ['P203', 'P210', 'P220']
h["primary"]["source"]                           # 'Regulation (EC) No 1272/2008 ...'
```

`found` is `False` when PubChem holds no classification, and the note points
at the supplier's safety data sheet instead. Silence is not "safe".

- `safety.py` — GHS labelling for one chemical, from PubChem.
- `coshh/rules.py` — H-codes to this form's ticks, each with its reason. No
  network, no Word.
- `coshh/manual.py` — a procedure in, an assessment dict out.
- `coshh/docx_form.py` — an assessment dict in, a filled .docx out.
- `app.py` — the web layer, and folding your corrections back in.

### Why each block names its source

Bodies disagree about the same substance. PubChem returns one block per
classifier, so each is kept apart and named, and the EU harmonised
classification is quoted first because GB CLP follows it. A code with no
source behind it is not worth copying onto a form somebody signs.

## Honest limits

- **It drafts; you sign.** Every route it takes — reading the manual, resolving
  a name, quoting a classification — can be wrong. The draft page exists so you
  catch that before the document does.
- **It quotes the published classification, including when that is nonsense.**
  Ask it about water and ECHA's aggregated registrant data says H315/H319/H335.
  That is what the source says, so that is what the row shows, with the source
  named and linked. Delete it on the draft page.
- **A name it cannot resolve gets a loud row**, not a blank one:
  `NO CLASSIFICATION FOUND - check the supplier's safety data sheet`. Type the
  codes in from the SDS and the draft records that they came from you.
- **Equipment is not a substance.** A rotary evaporator gets a row saying so and
  a note to assess the physical hazard by hand; it is never given a GHS
  classification it does not have.
- **Amounts are transcribed, never converted.** The number on the form is the
  number in the text.
- **It does not draw a reaction scheme.** It writes the procedure's own
  description into that box for you to draw over.
- **It does not judge scale or containment**, and it does not sign.

## Install and test

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover
```

183 tests, all offline: the PubChem layer runs against a trimmed fixture of its
response, and the reader and the web layer run with the model call and the
lookup injected. One live smoke test is skipped unless `COSHH_LIVE=1`.

Lookups are cached for a week; PubChem asks for no more than five requests a
second and no key. The reader uses `claude-sonnet-5` by default; override with
`COSHH_MODEL`.
