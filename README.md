# coshh-end

Hazard labelling for a chemical, from PubChem, free and without an API key.

**COSHH** (Control of Substances Hazardous to Health) is the assessment a UK
lab fills in before anyone uses a substance. Every one of them starts from
the same handful of facts: the pictograms, the signal word, the H numbers and
the P numbers. This fetches that part.

It is not the assessment. Scale, containment, spill and waste are judgements
about one procedure in one fume hood, and they stay with the chemist.

## Use

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

## Why each block names its source

Bodies disagree about the same substance. PubChem returns one block per
classifier, so each is kept apart and named, and the EU harmonised
classification is quoted first because GB CLP follows it. A code with no
source behind it is not worth copying onto a form somebody signs.

## Install and test

```bash
pip install -r requirements.txt
python -m unittest discover -s tests
```

The tests are offline, against a trimmed fixture of PubChem's response.
Lookups are cached for a week; PubChem asks for no more than five requests a
second and no key.

## Where it came from

Written for [paper-to-order](https://github.com/siyuncao/paper-to-order),
which turns a paper's experimental section into a checked order list, and
split out here so the hazard half can grow on its own.
