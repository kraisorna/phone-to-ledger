# DEMO.md — phone-to-ledger (3-minute hackathon demo)

Track: Indie Developer · Problem statement: Build for Your World ·
Meta models: SAM 3.1 (segment) + Muse Spark (extract) via Meta Model API.

## Prerequisites

```sh
pip install --upgrade pip   # venvs with pip < 23 skip the ptl entry point
pip install -e .
# MODEL_API_KEY resolves from env or .env automatically (never on camera)
```

## Script (3:00 total)

### 0:00–0:30 — Hook
Thai shops run on paper: faded thermal slips, ABB forms, 2-digit
Buddhist years. Bookkeepers retype them by hand. Show a phone photo of
a receipt → cut to the ledger CSV it becomes. One line: "photo in,
accountant-ready row out."

### 0:30–1:30 — Live pipeline (happy path)
Run the core path on the sample receipt (`demo/sample.jpg`, a Cafe
Amazon ABB slip; its expected row is `demo/expected.csv`):

```sh
ptl ingest demo/sample.jpg
ptl e2e demo/sample.jpg --out demo/out.json --csv demo/ledger.csv
# 15/16 columns match demo/expected.csv exactly; only source_image_ref
# is excluded (input-path-derived: sample.jpg vs s1.jpg). Money, tax ID,
# date, branch, and payment vocabulary all match live.
diff <(cut -d, -f1-14,16 demo/ledger.csv) <(cut -d, -f1-14,16 demo/expected.csv) \
  && echo LEDGER-MATCH
```

Fixture-backed beats (instant, offline-safe) if the live call stalls:

```sh
PYTHONPATH=src:. python3 -m unittest discover -s tests 2>&1 | tail -3   # 300 green
ptl validate --doc demo/s1.json        # S1 fixture dump, all rules pass
ptl export --doc demo/s1.json          # prints the ledger CSV row to stdout
```

Call out on camera: SAM 3.1 found the slip, Spark filled the schema,
money is integer satang with recomputed 7% VAT.

### 1:30–2:15 — It catches real errors (trust beat)
Validate a doctored doc (wrong line sum / bad tax ID) and show R1/R6
failing → `needs_review`, never silently accepted:

```sh
ptl validate --doc demo/bad_sum.json; echo "exit=$?"   # exit=2, R1 hard-fails
ptl review --queue demo/review/ --pending
```

(`demo/bad_sum.json` is S1 with the first line_total +100 satang.)

### 2:15–3:00 — Close
Recap the path (segment → extract → validate → export), who it serves
(Thai shops/bookkeepers drowning in paper), and what's next (faded
thermal, full-form invoices, Glimmer offline). End on the CSV.

## Fallback (no network / API down)

The 1:30–3:00 beats run fully offline (validate/export/review/tests use
no API). For the 0:30–1:30 live extraction, play the recorded run:
`demo/recorded_run.txt` holds one good live capture (exit=0,
auto_accept, 45.00 row). Screenshot `demo/expected.csv` for the close.
Live extraction varies run to run (2/3 green so far: one rerun came
back with control-char keys and dropped payments → blocked:R1), so
lead with the recording and keep live as the backup, not the opener.
Update: NUL-suffixed keys now auto-recover in `normalize_keys`
(replay-verified: that blocked run validates clean); fully-dropped
fields remain unrecoverable variance.

## TODO (demo-critical)

- [x] `demo/sample.jpg`: one clean Thai receipt photo + `demo/expected.csv`
- [x] `demo/s1.json`: S1 fixture dumped from `tests/fixtures.py`
- [x] `demo/bad_sum.json`: S1 with a corrupted total (trust beat)
- [x] e2e entry point (`ptl e2e`: segment→extract→validate→export in one command)
- [x] `demo/recorded_run.txt` fallback capture
- [ ] Record + edit the 3-minute video (primary judging artifact)
