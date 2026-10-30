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
ptl e2e image.jpg --out result.json --csv ledger.csv [--seen seen.json]
  [--concept receipt] [--api-key ...]
ptl eval --preds preds.json --labels data/labels --faded-ids faded.txt
ptl baseline --system {a,b,c,d} --images imgdir --out preds.json
ptl review --queue review/ --pending   # or --show/--resolve/--export-labels
ptl ingest image.jpg
```

Exits: `validate` → 2 when human review needed; `export` → 3 when every
doc was excluded as duplicate; `e2e` → 2 needs review, 3 no rows, 4 no
receipts found.

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

- Cloud (`sam31`, `spark`) resolves `MODEL_API_KEY` via
  `ptl.adapters.env.resolve_secret`: explicit `api_key=` first, then
  process env, then nearest `.env` walking up from cwd. No manual
  export needed. Both are live-verified against
  `https://api.meta.ai/v1` (`sam-3.1`, `muse-spark-1.3`).
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

## Hackathon — Meta Global AI Developer Hackathon (Cerebral Valley)

Sources: `docs/hackathon/*.eml` (entry APPROVED) + saved `Details…
.mhtml` (full Participant Guide). Track: **Indie Developer**
(confirmed; $400K pool: 150/100/75/50/25K). Problem statement:
"Build for Your World" (Meta models in your domain).

- Window: Mon Oct 26 12:00 PM ET → **Wed Nov 4 9:00 PM EST** (Thu Nov
  5 02:00 UTC = 09:00 Bangkok). Tue Nov 3 is the last day for
  submission questions/troubleshooting. Judging Nov 5–8; closing Nov 9.
- Submission (one per team, via CV platform, Representative submits):
  public repo accessible + **3-minute demo video** (primary judging
  artifact with code + live product) + everyone listed. Late = out.
- Judging: Stage 1 pass/fail (fits theme + reasonably used Meta Model
  API / open weights). Stage 2: Impact 30%, Meta tooling 25%,
  Technical depth 20%, Demo 25%. Top 5/track to live finals.
- Bonus fits: Best Agentic $5K (validate/triage agent), Best Open
  Weight $10K (needs the Glimmer path real), Most Viral $20K (demo on
  X by Nov 8 EOD), Community Vote $10K.
- Credits: $150 Meta Model API claimed. Status Oct 31: **$121.18
  left** ($28.82 used; billing lags ~1h). No payment method on file,
  so spend hard-stops at $0 — do not ask for one. Email spend alerts
  not yet set up (user to click Set up). Partners: Baseten/Modal/
  Fireworks $100 each (Baseten model:
  `meta-models/muse-spark-open-1026`).

Compliance (disqualification risk — never break these):

- Repo must stay PUBLIC (verified). Nothing unlicensed (code/data).
- NEW WORK ONLY: demo/video/submission may highlight ONLY what was
  built Oct 26–Nov 4. Verified: all commits here are Oct 28+ (clean).
  Never merge in pre-event code/data (incl. `../rapee` specs/samples
  or old fixtures) without telling the user it must be excluded from
  demo claims — judges disqualify unclear originality at their sole
  discretion.

Alert the user in your final message whenever ANY of these holds:

1. A submission piece is missing or stale: demo video, DEMO.md,
   README quickstart, public-repo access, contributor list.
2. Work touches submission readiness: live demo path, license,
   secrets exposure, track/problem-statement framing.
3. The deadline is within 48h — lead with time remaining and cut scope
   to demo-critical items only; within 24h — say so in the first line.
4. A task risks the deadline (long eval batches, bulk API spend,
   refactors, Glimmer rabbit holes) — flag it before starting.
5. Anything pre-dating Oct 26 enters the tree — stop and disclose.
