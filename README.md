# coshh-end

A list of substances — or a whole lab manual — goes in; a filled-in COSHH form
comes out as a Word document, for a competent person to check and sign.

**COSHH** (Control of Substances Hazardous to Health) is the assessment a UK
lab fills in before anyone uses a substance. Every one of them starts from
the same handful of facts: the pictograms, the signal word, the H numbers and
the P numbers. This fetches that part from PubChem, free and without an API
key, works out which of the form's boxes those codes argue for, and writes
them onto the form — the neutral one this repo ships, or your own.

It is not the assessment. Scale, containment, spill and waste are judgements
about one procedure in one fume hood, and they stay with the chemist.
`Approved By` is left blank, and the writer refuses to save a form with
anything in it. Every generated document says so on its face: the
`Special measures:` cell carries a dated line naming the tool and the data
source, followed by everything still unresolved, so a printed form cannot be
mistaken for a checked one.

## The app

Python 3.9 or newer (`anthropic` and `fastapi` both need it — on older
versions the second line below fails with a pip resolution error that says
nothing about Python versions). Check with `python3 -V`, and name the
interpreter explicitly if your `python3` is older:

```bash
python3 -m venv .venv                 # or python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app:app --port 8000
```

Then open <http://127.0.0.1:8000>. No key, no account, no database.

### Two ways in, and only one of them costs anything

Reading prose is the only step in this tool that needs a language model.
PubChem, the rule table and the document are deterministic, offline-ish and
free, so they are on the near side of that line:

| | needs a model | needs a key |
|---|---|---|
| **A substance list** — one per line, `pyrrolidine 7.11 g`, `3 M HNO3 20 mL` | no | no |
| **A pasted procedure** — the prose of a method, substances read out of it | yes | yes, yours |

The list path is the default because it is the one that asks nothing of you.
A few lines of Python split each line into a name and an amount; everything
after that — the PubChem lookup, the ticks, the .docx — is the same code
either way.

**Whose key pays.** The procedure path takes an Anthropic API key from a
password box on the page. It is your key and it pays for your own call: it
is sent with that one request, used for that one model call, and then gone.
It is never written to disk, never logged, never put in a web address and
never rendered back into a page — including into an error message, which is
scrubbed before it is shown. The only place it is kept is your own browser's
`localStorage`, so you need not retype it, and clearing your site data
clears it. The page is a single form, so the key box is disabled before a
submit that carries a substance list: the keyless path never puts a
credential on the wire. Get one at
<https://console.anthropic.com/settings/keys>.

These promises are about the copy you run. Run it yourself on localhost; do
not paste your key into somebody else's instance, and if you do host it,
serve it over HTTPS — a password field on plain HTTP is a password in clear.

If the process running the app has `ANTHROPIC_API_KEY` set — you, running it
on your own machine — that key is used instead, the box becomes optional and
the page says the server is paying. Running it without one is fine: the list
path never asks for a key at all.

```bash
export ANTHROPIC_API_KEY=...          # optional: only for the procedure path
.venv/bin/uvicorn app:app --port 8000
```

Three pages, and the gap between the second and the third is the point:

| | |
|---|---|
| `GET /` | List the substances, or paste the experimental procedure / upload a `.txt` / `.docx`, and fill in Title, Name, Date, Department, Year. |
| `POST /draft` | Shows what was read: every substance, its amount transcribed word for word, its H-codes with the source named and linked, and every box that will be ticked, with anything PubChem could not classify shouted at the top. **Everything on this page is editable.** |
| `POST /document` | Turns *the corrected draft* into the .docx and hands it back as a download. |

The tool never goes from what you typed to Word in one step. PubChem answers
the lookups, and on the procedure path a language model reads the prose; both
can be wrong, and a COSHH form is a document somebody signs. So it shows its
work, you correct it, and only then is there a file.

Nothing is persisted. The manual you paste is held for the length of the
request; the document is built in a temporary file, read into memory, and the
file is unlinked before the response is sent.

### The form it writes onto

It ships with one, so there is nothing to supply:

```
templates/generic-coshh-template.docx
```

A *COSHH Form, Teaching Laboratory* belonging to no institution — headed
"COSHH Form / Teaching Laboratory", asking for a **Department**, telling a
spill to a **supervisor**. That is the only `.docx` in the repository. Every
other `templates/*.docx` is git-ignored, because a college's own form is its
own document and this repo is public.

Neutral inside the zip as well as on the page: a `.docx` carries
`dc:creator`, `cp:lastModifiedBy` and `Company` in `docProps/`, where `grep`
cannot see them. The shipped form's are empty, and the writer strips those
three from every document it saves, so your own template does not hand its
author's name to whoever you give the form to either.

To use your own form instead, point `COSHH_TEMPLATE` at it:

```bash
COSHH_TEMPLATE=~/my-coshh-form.docx .venv/bin/uvicorn app:app --port 8000
```

or drop it at `templates/coshh-template.docx`, which `.gitignore` still
excludes. A form that says "demonstrator" where the shipped one says
"supervisor" still gets that tick — the control-measure lookup ignores which
word a form uses for the person in charge — but a control measure the form
does not offer at all is refused rather than quietly dropped.

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

Three outcomes, not two, because they send you to different places:

| | `found` | `cid` | what the row says |
|---|---|---|---|
| classified | `True` | a number | the codes, with the source and CID beside them |
| known, unclassified | `False` | a number | `NO CLASSIFICATION FOUND` — read the SDS |
| name resolved to nothing | `False` | `None` | `NAME NOT RESOLVED` — search by CAS number |
| lookup never answered | `False` | `None`, `unreachable` | `NOT CHECKED` — and it is not cached, so the next draft retries |

The last one matters under `uvicorn`: one network blip used to freeze "no
classification" for that substance for the life of the process.

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
- **A substance it cannot classify gets a loud row**, not a blank one, and its
  ticks match: every exposure route, plus gloves and the fume hood, because an
  unassessed row with nothing ticked reads as "considered, and there is no way
  in". Type the codes in from the SDS and the draft records that they came from
  you; empty the box entirely and the banner comes back.
- **Every row names its source.** The Hazards cell carries the classifier, the
  PubChem CID and the compound title PubChem actually resolved to, because its
  name resolver substitutes silently: ask it about `PEG` and it answers with
  CID 174, ethylene glycol.
- **A substance read as "mentioned, not used" still gets a row**, marked as
  unassessed. If the reader was wrong, that is visible on the paper rather than
  missing from it.
- **Equipment is not a substance.** A rotary evaporator gets a row saying so and
  a note to assess the physical hazard by hand; it is never given a GHS
  classification it does not have.
- **Amounts are transcribed, never converted.** The number on the form is the
  number in the text.
- **A line that names two substances gets one row and says so.** `sodium
  borohydride 1.2 g in 10 mL MeOH` is read as one substance, because rejoining
  the text is the best guess a regular expression can make — and the leftover
  words go into the review asking you to give the second reagent its own line.
  Nothing is folded into a name silently.
- **The waste stream can be read off a name, and says when it was.** Benzyl
  bromide goes to the halogenated bottle because the name is an organic halide,
  not because anything classified it; the review line says so and still asks a
  technician.
- **It does not draw a reaction scheme.** It writes the procedure's own
  description into that box for you to draw over.
- **It does not judge scale or containment**, and it does not sign.
- **Your key buys one call, not a promise.** The procedure path is only as good
  as the model reading it, and it is your key that pays for the attempt —
  including an attempt that comes back wrong. The list path costs nothing and
  asks nothing of a model, which is why it is the default.
- **The shipped form is a form, not your form.** If your department's COSHH
  paperwork differs — different tables, different control measures — point
  `COSHH_TEMPLATE` at yours; see `docs/template-anatomy.md` for what the writer
  assumes.

## Install and test

```bash
python3 -m venv .venv                 # Python 3.9 or newer
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover
```

314 tests, all offline: the PubChem layer runs against a trimmed fixture of its
response, and the reader and the web layer run with the model call and the
lookup injected. One live smoke test is skipped unless `COSHH_LIVE=1`; nothing
else needs a key or a network.

Because the neutral form is committed, the tests that open or produce a .docx
run on a fresh clone — including the one that writes a document from the
shipped template and reads the XML back to check the ticks.

Lookups are cached for a week; PubChem asks for no more than five requests a
second and no key. The reader uses `claude-sonnet-5` by default; override with
`COSHH_MODEL`.
