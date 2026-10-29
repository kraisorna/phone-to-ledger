# phone-to-ledger (ptl)

Photo-to-ledger pipeline for Thai tax invoices / receipts / ABB slips:
phone photo -> ingest -> segment -> extract -> validate -> export.

## Layout

- `src/ptl/schema/` — extraction schema JSON (v1.0) + loader
- `src/ptl/money.py` — satang-int money + VAT helpers (700bp, half-up)
- `src/ptl/pipeline/` — `ingest`, `segment`, `quality`, `extract`,
  `validate_rules` (R1-R12 pure fns), `triage`, `export`
- `src/ptl/adapters/` — `base` interfaces + live `sam31` /
  `spark` (Meta Model API, `MODEL_API_KEY` from env or `.env`), `glimmer`
  stub, working `tesseract` baseline
- `src/ptl/review/queue.py` — human review queue
- `src/ptl/api/cli.py` — `ptl` CLI entry
- `src/ptl/eval/` — scorer + eval runner + baselines A-D
- `tests/` — rule/schema/seed-fixture tests
- `data/` — `dev/`, `test/`, `labels/` (read-only, DVC-managed; not committed).
  See `data/COLLECTION.md` for the collection protocol.

## Quickstart

```sh
pip install -e .
ptl validate --doc path/to/doc.json
ptl export --doc path/to/doc.json --out ledger.csv
ptl eval --preds eval/preds.json --labels data/labels --faded-ids faded.txt
ptl review --queue review/ --pending
make test
```

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
