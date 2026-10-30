# DEMO.md — phone-to-ledger (3-minute hackathon demo)

Track: Indie Developer · Problem statement: Build for Your World ·
Meta models: SAM 3.1 (segment) + Muse Spark (extract) via Meta Model API.

## Prerequisites

```sh
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
Run the core path on the sample receipt (TODO: add
`demo/sample.jpg` + expected `demo/expected.csv`):

```sh
ptl ingest demo/sample.jpg
ptl e2e demo/sample.jpg --out demo/out.json --csv demo/ledger.csv
```

Until the e2e CLI lands, the shippable live beats are fixture-backed:

```sh
PYTHONPATH=src:. python3 -m unittest discover -s tests 2>&1 | tail -3   # 246 green
ptl validate --doc demo/s1.json        # TODO: dump S1 fixture to demo/s1.json
ptl export --doc demo/s1.json          # prints the ledger CSV row to stdout
```

Call out on camera: SAM 3.1 found the slip, Spark filled the schema,
money is integer satang with recomputed 7% VAT.

### 1:30–2:15 — It catches real errors (trust beat)
Validate a doctored doc (wrong line sum / bad tax ID) and show R1/R6
failing → `needs_review`, never silently accepted:

```sh
ptl validate --doc demo/bad_sum.json; echo "exit=$?"
ptl review --queue demo/review/ --pending
```

TODO: add `demo/bad_sum.json` (S1 with line_total corrupted).

### 2:15–3:00 — Close
Recap the path (segment → extract → validate → export), who it serves
(Thai shops/bookkeepers drowning in paper), and what's next (faded
thermal, full-form invoices, Glimmer offline). End on the CSV.

## Fallback (no network / API down)

The 1:30–3:00 beats run fully offline (validate/export/review/tests use
no API). For the 0:30–1:30 live extraction, play the recorded run:
TODO: capture one good `demo/recorded_run.txt` (command + output) and
screenshot the CSV.

## TODO (demo-critical)

- [ ] `demo/sample.jpg`: one clean Thai receipt photo + `demo/expected.csv`
- [ ] `demo/s1.json`: S1 fixture dumped from `tests/fixtures.py`
- [ ] `demo/bad_sum.json`: S1 with a corrupted total (trust beat)
- [x] e2e entry point (`ptl e2e`: segment→extract→validate→export in one command)
- [ ] `demo/recorded_run.txt` fallback capture
- [ ] Record + edit the 3-minute video (primary judging artifact)
