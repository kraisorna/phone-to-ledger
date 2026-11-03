# phone-to-ledger (ptl)

Photo-to-ledger pipeline for Thai tax invoices / receipts / ABB slips:
phone photo -> ingest -> segment -> extract -> validate -> export.

## Built during the hackathon

Meta Global AI Developer Hackathon (Indie Developer track). Building
period Oct 27 – Nov 4, 2026; this repository's first commit is
Oct 28, 2026.

**Built during the event (everything in this repo):** all code in
`src/ptl/` — ingest + PII scrub, SAM 3.1 segmentation and Muse Spark
extraction adapters, the offline Muse Glimmer adapter, extraction
prompts, satang money/VAT math, validation rules R1–R14, triage,
dedup, review queue + review page, CSV/XLSX export, CLI — plus the
test suite, the 25 hand-transcribed gold labels
(`src/ptl/eval/gold.py`), the eval harness and baselines A–D, and
the demo materials.

**Existed before the event (not counted as hackathon work):**

- Personal design notes written Aug 29–30, 2026 (product plan,
  Thai document model, OCR edge-case list, a draft extraction
  schema, a phase-1 flow). They are not in this repo. The schema
  in `src/ptl/schema/` is based on that draft; its loader and
  checks, and every other part of the pipeline, were written
  during the event. The OCR pipeline plan was written Oct 27.
- Receipt photos: the author's own phone photos of everyday
  purchases. 20 of the 36 were taken Aug 27 – Oct 3, 2026, and 16
  were taken Oct 30–31. Only one is in this repo
  (`demo/sample.jpg`, taken Aug 27, PII-redacted). The photos are
  input data only; the gold transcriptions of them were made
  during the event.

## Layout

- `src/ptl/schema/` — extraction schema JSON (v1.0) + loader
- `src/ptl/money.py` — satang-int money + VAT helpers (700bp, half-up)
- `src/ptl/pipeline/` — `ingest`, `segment`, `quality`, `extract`,
  `validate_rules` (R1-R14 pure fns), `triage`, `export`, `dedup`
- `src/ptl/adapters/` — `base` interfaces + live `sam31` /
  `spark` (Meta Model API, `MODEL_API_KEY` from env or `.env`), working
  `tesseract` baseline; `glimmer` offline extraction via local Ollama,
  corpus-measured (4/25 docs, grand totals 25/25)
- `src/ptl/review/queue.py` — human review queue
- `src/ptl/api/cli.py` — `ptl` CLI entry
- `src/ptl/eval/` — scorer + eval runner + baselines A-D
- `tests/` — rule/schema/seed-fixture tests
- `data/` — `dev/`, `test/`, `labels/` (read-only, DVC-managed; not committed).
  See `data/COLLECTION.md` for the collection protocol.

## Quickstart

```sh
pip install -e .
ptl e2e photo.jpg --out result.json --csv ledger.csv
ptl validate --doc path/to/doc.json
ptl export --doc path/to/doc.json --out ledger.csv
ptl labels --out data/labels   # regenerate the 25 gold labels (gitignored)
ptl baseline --system a --images <images-dir> --out /tmp/preds_a.json
ptl eval --preds /tmp/preds_a.json --labels data/labels --faded-ids data/faded.txt
ptl review --queue demo/review/ --pending   # seeded trust-beat record
make test
```

Demo: [DEMO.md](DEMO.md) is the 3-minute hackathon script (exact
commands, expected outputs, no-network fallback); `demo/sample.jpg`
+ `demo/expected.csv` keep one receipt and its ledger row in-repo.

## Eval

25 hand-transcribed gold seeds (S1–S25) + 3 pinned re-photo dedup
pairs, regenerated via `ptl labels`; faded-thermal split (S5/S17)
reported separately. Field-exact scores, 25/25 docs scored:

| system | docs | grand | lines | tax ID | dates |
| --- | --- | --- | --- | --- | --- |
| A Tesseract + regex | 0/25 | 8/25 | 0/25 | 9/25 | 4/25 |
| B single-prompt Spark | 6/25 | 23/25 | 10/25 | 23/25 | n/m¹ |
| C full pipeline (SAM + Spark + rules) | 7/25 | 25/25 | 15/25 | 25/25 | 25/25 |
| D Glimmer offline | 4/25 | 25/25 | 13/25 | 23/25 | 11/25 |

C details: form/discount also 25/25, docno 24/25 (S11 lone miss),
branch 23/25, legal 16/25. Faded docs fully correct: C 1/2 (S5),
B 1/2 (S5), D 0/2 (S5 takes 6/12 fields), A 0/2.
Doc-level misses are dominated by
Thai tone-mark confusions and dropped digits in verbatim prose —
recorded model limitations, never papered over in post-processing.
`ptl eval` also reports the review cross-tab (review rate,
auto-accept accuracy, flag recall); on the 25 seeds the pipeline
flags 11 and auto-accepts 14/14 exactly right.

¹ B dates not measured: single-prompt preds were not retained
when B ran, and re-running B costs 25 paid Spark calls — queued
until the next paid baseline refresh, not silently filled.

## Rules

- Money stored as integer **satang**, exported as THB with 2 decimals.
- VAT rate 700bp; inclusive `vat=round(total*7/107)`, exclusive
  `round(vatable*7/100)`, half-up at document level.
- R1-R6 fail => never auto-post; corrections via credit/debit note only.
- R13 completeness floor (grand, lines, date) => sparse extractions
  go to review, never auto-post.
- ABB (`form=abbreviated`) kept but marked `can_claim_input_vat=false`.
- PII masked at ingestion (PDPA); low-confidence docs go to review,
  never silently accepted.
- R10 duplicates need a seen-store: `export --seen seen.json` records
  accepted docs and excludes repeats (stderr note, exit 3);
  `validate --seen` only flags.
