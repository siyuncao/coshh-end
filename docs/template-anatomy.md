# COSHH template anatomy

How the *COSHH Form, Chemistry Teaching Laboratory* `.docx` is built, and how to
fill it programmatically. Every claim below was produced by running code against the file
(`python-docx` + `lxml`, plus raw `unzip` of the OPC package) and re-verified by writing a
document and re-opening it.

Template lives at `templates/coshh-template.docx` (git-ignored — the user supplies their own).

## The checkboxes: both a glyph AND a content control

Counted in `word/document.xml`: **90 `w:sdt`**, of which **86 carry a `w14:checkbox`**.
`<w:sym>`: 0. Legacy `<w:checkBox>` form fields: 0. Literal glyph counts in the raw XML:
`☐ U+2610` x65, `☒ U+2612` x21, `☑ U+2611` x0 — 65 + 21 = 86, exactly one glyph per box.

So the glyph *is* a literal character in a run, but that run lives inside `<w:sdtContent>`
and its state is mirrored in `<w:sdtPr>`:

```xml
<w14:checkbox>
  <w14:checked        w14:val="0"/>          <!-- "1" = ticked -->
  <w14:checkedState   w14:val="2612" w14:font="MS Gothic"/>
  <w14:uncheckedState w14:val="2610" w14:font="MS Gothic"/>
</w14:checkbox>
```

**Swapping the character alone is not enough** — `w14:checked` would disagree with the
glyph and Word re-renders the box from the control. Always write both. Measured states:
`(checked=1, 2612, 2610, MS Gothic)` x21 and `(checked=0, 2612, 2610, MS Gothic)` x65 —
completely uniform, so the hex values can be read from the element rather than hardcoded.

**No run-splitting problem for the glyph.** Each `<w:sdtContent>` holds exactly one `w:r`
with exactly one `w:t` (measured: `{1: 86}` for both counts).

**Font drift is real.** 81 glyph runs carry `rFonts ascii/hAnsi="MS Gothic" hint="eastAsia"`,
but 5 carry `Segoe UI Symbol` — Word rewrote them when a human toggled those boxes. Set
`ascii`/`hAnsi`/`eastAsia` from `w14:checkedState|uncheckedState/@w14:font` on every write.

## Two traps that will bite

**1. `python-docx` under-reports cells.** Four cells are wrapped as
`<w:sdt><w:sdtContent><w:tc>` (cell-level content controls). `python-docx` walks `w:tr` for
*direct* `w:tc` children, so the substance table's example row reported **2 cells for a
5-column row**. Any cell accessor must unwrap `w:sdt` -> `w:sdtContent` -> `w:tc`.

**2. Never call lxml `itertext()` on python-docx elements.** `w:tc`, `w:p` and `w:r` each
expose a python-docx `.text` property that `itertext()` picks up, so `"Title:"` reads back
as `"Title:Title:Title:"`. Use `el.iter(W+'t')` and join `.text`.

## Body layout

`body` children: `tbl, p, tbl, p, tbl, p, tbl, p, tbl, p, tbl, p, sectPr` — six tables at
indices 0-5 with empty spacer paragraphs between. The `COSHH Form / Chemistry Teaching
Laboratory` banner is in `word/header1.xml`, not the body. No `w:documentProtection`.

### Table 0 — header fields (3 rows)

| cell | content |
|---|---|
| `[0][0]` / `[0][1]` | `Title:` / **Title value** (`gridSpan=3`) |
| `[1][0]` / `[1][1]` | `Name:` / **Name value** |
| `[1][2]` / `[1][3]` | `Date:` / **Date value** |
| `[2][0]` / `[2][1]` | `College:` / **College value** |
| `[2][2]` / `[2][3]` | `Year:` / `1  /  2  /  3` |

Verified: each of the four value cells holds **exactly one `w:p`, with a `w:pPr` and zero
runs**. Writing is therefore *append a run to the existing paragraph* — do not create a new
paragraph and do not touch `pPr`; spacing and style are inherited.

The Year cell holds one bold run `'1  /  2  /  3'`. To mark a year, replace it with five
runs `'1'`, `'  /  '`, `'2'`, `'  /  '`, `'3'`, deep-copying the original `rPr` into each
and adding `<w:u w:val="single"/>` to the chosen one. Verified on the written file: the
cell still reads `1  /  2  /  3` and only `'2'` carries `underline=single`.

### Table 1 — Reaction Scheme (2 rows)

`[0][0]` label `Reaction Scheme:`; `[1][0]` is `gridSpan=2` and is a **cell-level `w:sdt`**
with `<w:temporary/>` + `<w:showingPlcHdr/>` and grey italic placeholder text
*"(Write out your reaction scheme(s) here...)"*.

To write here: unwrap the `w:sdt` to its bare `w:tc`, keep only the first paragraph, delete
its runs, and strip `rStyle=PlaceholderText`, `w:color` and `w:i` from `pPr/rPr` — otherwise
the text renders grey and italic. Natural home for a ChemDraw image later.

### Table 2 — substance table (6 rows x 5 cols)

Header row 0: `Substances/ Equipment Used | Mass/Volume | Hazards | Exposure Route |
Control Measures`.

* **Row 1 is the worked example.** Cells 0, 1, 2 are cell-level `w:sdt` placeholders
  (`showingPlcHdr`): `e.g. 3 M HNO3` / `20 mL` / `H272 ... H290 ... H331 ... H314`.
  Cells 3 and 4 are ordinary cells with demo ticks (Eyes, Skin, Inhalation; and spill,
  spectacles, lab coat, gloves, fumehood, ignition).
* **Rows 2-5 are the four blank rows.** Cells 0-2 empty; Exposure Route all unticked;
  Control Measures pre-ticked **spill advice, Safety spectacles, Lab coat** — the
  department's always-on default. Preserve that default when cloning.
* Template totals: 86 checkboxes, 21 ticked.

**Keep or remove the worked example?** *Remove it by default.* Word prints content-control
placeholder text, so a handed-in form would still show grey `e.g. 3 M HNO3`. Deleting the
whole `w:tr` is one call and leaves rows 2-5 as clean prototypes. Expose `keep_example=False`
as the default with an opt-in.

**Cloning for N substances:** use the **first genuinely blank row** as the prototype, never
row 1 (placeholder SDTs + demo ticks). `copy.deepcopy(tr)`, then **regenerate every
`w:sdtPr/w:id`** in the clone to a fresh random int32 before `last.addnext(clone)` —
duplicate SDT ids are what makes Word complain. Verified at N=8: 9 rows, 132 SDTs,
132 unique ids, all checkbox lists intact, zip valid, every part re-parses.
`w14` is declared on `<w:document>` and survives deepcopy, so no namespace registration is
needed.

Exposure Route cell `[r][3]` — label **before** the box, one box per paragraph, with an
empty paragraph sitting between `Skin` and `Inhalation`:

```
Absorption:        (paragraph, no checkbox)
Eyes ☐   Skin ☐   (empty p)   Inhalation ☐   Ingestion ☐
```

Control Measures cell `[r][4]` — label **after** the box, 11 fixed options, in order:

1. `In case of spill, consult a demonstrator, technician or senior member of staff`
2. `Safety spectacles`
3. `Lab coat`
4. `Gloves`
5. `Fumehood`
6. `Keep away from naked flames and sources of ignition`
7. `Heat using temperature-controlled water bath`
8. `Not to be used if pregnant`
9. `Do not store or use near water (store in oil)`
10. `Add dropwise to solution`
11. `Do not expose to air`

Because the label precedes the box in one cell and follows it in the other, resolve a box's
label as **`"".join(runs before the sdt) + "".join(runs after the sdt)` within its own
`w:p`, then `.strip()`**. Verified to return all 11 labels above and all 4 route labels
exactly. This survives runs split mid-label and never confuses two options, because each
option is its own paragraph holding exactly one checkbox.

### Table 3 — Specific Safety or Risk Implication (6 rows x 3 cols)

Header: `Specific Safety or Risk Implication: | Y | If Yes, Prevention Measures:`.
There is **one `Y` box per row, not a Y/N pair** — "no" is simply an unticked box.

Rows 1-5: `Fire or Explosion`, `Thermal Runaway`, `Gas Release`, `Malodorous Substances`,
`Special measures:`. The box is in `[r][1]`, its label in `[r][0]` — a **different cell**,
so paragraph-local label lookup returns `""` here. Address by row index instead.

### Table 4 — Waste Disposal (4 rows x 4 cols)

Row 0: `Waste Disposal:` (`gridSpan=2`) plus a free-text cell (`gridSpan=2`).
Rows 1-3 are box/label pairs **across cells**: box in col 0 -> label in col 1,
box in col 2 -> label in col 3.

| row | col 0 / 1 | col 2 / 3 |
|---|---|---|
| 1 | Halogenated | Aqueous |
| 2 | Hydrocarbon | Named Waste |
| 3 | Contaminated solid waste | Silica/TLC |

Label cells carry trailing padding spaces (`'Aqueous                    '`) — strip before
comparing. Address by (row, col) rather than by label lookup.

### Table 5 — Approved By (1 row x 4 cols)

`Approved By: | <blank> | Date: | <blank>`. **Leave both blank, always.** This is the
competent person's signature; the generator must never fill it.

## Constants

```python
W   = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
W14 = "{http://schemas.microsoft.com/office/word/2010/wordml}"
CHECKED, UNCHECKED = "☒", "☐"   # U+2612 BALLOT BOX WITH X, U+2610 BALLOT BOX
TABLE_HEADER, TABLE_SCHEME, TABLE_SUBSTANCES = 0, 1, 2
TABLE_RISK, TABLE_WASTE, TABLE_APPROVAL      = 3, 4, 5
SUBSTANCE_HEADER_ROW, EXAMPLE_ROW = 0, 1
COL_NAME, COL_AMOUNT, COL_HAZARDS, COL_ROUTE, COL_CONTROL = 0, 1, 2, 3, 4
EXPOSURE_ROUTES = ("Eyes", "Skin", "Inhalation", "Ingestion")
RISK_ROWS = {"Fire or Explosion":1, "Thermal Runaway":2, "Gas Release":3,
             "Malodorous Substances":4, "Special measures":5}
WASTE_CELLS = {"Halogenated":(1,0), "Aqueous":(1,2), "Hydrocarbon":(2,0),
               "Named Waste":(2,2), "Contaminated solid waste":(3,0), "Silica/TLC":(3,2)}
```

## Evidence

| file | parts | checkboxes | ticked | sdt ids | unique | tc outside tr/sdtContent | state/glyph mismatch |
|---|---|---|---|---|---|---|---|
| template | 23 | 86 | 21 | 90 | 90 | 0 | 0 |
| generated | 23 | 131 | 39 | 132 | 132 | 0 | 0 |

The generated file was produced by: deleting the worked-example row, cloning the prototype
out to 8 data rows, writing Title/Name/Date/College, underlining Year 2, filling three
substances (one deliberately carrying `NO GHS CLASSIFICATION FOUND IN PUBCHEM - ASSESS
MANUALLY`), ticking Gas Release with a prevention note, ticking Halogenated + Aqueous waste,
and leaving Approved By empty. Re-opened with `python-docx`: every header value read back
verbatim, the sulfuric-acid row's ticked controls read back as the three department defaults
plus `Gloves`, `Fumehood`, `Add dropwise to solution`, zip valid, and
`word/document.xml` / `word/settings.xml` / `[Content_Types].xml` all re-parse.
