# AGENTS.md — phone-to-ledger (`ptl`)

Thai tax invoice / receipt / ABB slip pipeline: phone photo → ingest →
segment → extract → validate → export (ledger CSV).

## Layout

- `src/ptl/schema/` — extraction schema v1.0 JSON + stdlib-only loader
  (`load_schema`, `check_structure`, `derive_claim_flag`)
- `src/ptl/money.py` — satang-int money + VAT helpers (700bp, half-up)
- `src/ptl/pipeline/` — `ingest`, `segment` (Crop model), `quality`,
  `extract` (prompt rules + post-processing), `validate_rules` (R1–R14 pure
  fns), `triage`, `export`, `dedup` (seen-store)
- `src/ptl/adapters/` — `base` interfaces + `sam31`, `spark`, `glimmer`,
  `tesseract` backends
- `src/ptl/eval/` — scorer + eval runner + baselines A–D
  (README's top-level `eval/` path is stale; the package lives here)
- `src/ptl/review/queue.py` — human review queue
- `src/ptl/api/cli.py` — `ptl` CLI entry (`ptl = "ptl.api.cli:main"`)
- `tests/` — unittest suite (mocked HTTP; no live API calls)
- `data/` — `dev/`, `test/`, `labels/` (read-only, DVC-managed, not
  committed)

Reference specs live OUTSIDE this repo (read-only context):
`../rapee/docs/` (`00`–`05` + `README.md` + `samples/`).

## Commands

```sh
pip install -e .          # or: PYTHONPATH=src
make test                 # unittest discover — keep this green
make lint                 # compileall over src + tests
ptl validate --doc doc.json [--seen seen.json] [--force]
ptl export --doc doc.json [...] --out ledger.csv [--seen seen.json] [--append]
ptl eval --preds preds.json --labels data/labels --faded-ids faded.txt
ptl baseline --system {a,b,c,d} --images imgdir --out preds.json
ptl review --queue review/ --pending   # or --show/--resolve/--export-labels
ptl ingest image.jpg
```

Exits: `validate` → 2 when human review needed; `export` → 3 when every
doc was excluded as duplicate. No `segment`/`extract` CLI yet — adapters
are used programmatically.

## Hard invariants (do not break)

- Money is integer **satang** internally, THB with 2 decimals only at
  export. VAT 700bp; inclusive `vat=round(total*7/107)`, exclusive
  `round(vatable*7/100)`, half-up at document level. Recompute VAT —
  never trust printed VATable/VAT figures.
- R1–R6 fail ⇒ never auto-post; corrections via credit/debit note only.
  Triage may NOT edit values to pass, clear an R1–R6 fail, or guess.
- `form=abbreviated` only with an explicit ABB mark; full only with buyer
  name+address+tax ID on the slip; else `unknown`. ABB keeps
  `can_claim_input_vat=false`.
- PII masked at ingestion (PDPA); low-confidence docs go to the review
  queue, never silently accepted. Partial captures marked, never
  extracted as complete.
- R10 duplicates: `export --seen seen.json` records accepted docs and
  excludes repeats (stderr note, exit 3); `validate --seen` only flags.
- Stdlib only — `pyproject.toml` declares zero dependencies. New deps
  need explicit discussion.
- `.env` holds `MODEL_API_KEY` and is gitignored. Never commit keys,
  never print key values (length checks only).

## Adapters

- Cloud (`sam31`, `spark`) needs `MODEL_API_KEY` in the environment (or
  `api_key=...`); there is no `.env` loader, so `set -a; source .env;
  set +a` first. Both are live-verified against `https://api.meta.ai/v1`
  (`sam-3.1`, `muse-spark-1.3`).
- `sam31`: one image + concept `"receipt"` → one Crop per box, polygons
  in source pixels. Raises loudly on 401/404/grammar drift.
- `spark`: structured-output extraction → `(doc, {})`. Whole source
  image is sent (no crop rendering yet) — one photo per receipt.
- `glimmer`: offline stubs (`NotImplementedError`); needs local
  `model_path` wiring. `GlimmerReviewer` delegates to `triage()`.
- `tesseract`: system-A baseline; needs the `tesseract` binary with
  `tha+eng` data.

## Working agreements

- An hourly automation shares this tree: keep diffs focused, run `make
  test` before finishing, and leave the tree green.
- Commit each finished, locally tested unit of work (`make test` green
  first); one focused change per commit. Push only when explicitly asked.
- Prove behavior changes by measurement (rule outcomes, extraction
  accuracy on fixtures/samples, e2e smoke), not by description.
- Keep live API spend trivial: tiny probes, mocked tests, no bulk
  batches without need.

## Known gaps (current)

Eval labels + 150-receipt collection, S7–S11 fixtures, export target
format decision, Glimmer model wiring, crop renderer for Spark.
