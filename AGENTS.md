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
  (--out/--csv ending .xlsx writes a workbook instead; --append is CSV-only)
ptl e2e image.jpg --out result.json --csv ledger.csv [--seen seen.json]
  [--concept receipt] [--api-key ...] [--review-queue review/]
  [--attempts N, default 2]
ptl eval --preds preds.json --labels data/labels --faded-ids faded.txt
ptl baseline --system {a,b,c,d} --images imgdir --out preds.json
ptl labels --out data/labels   # regenerate gold from src/ptl/eval/gold.py
ptl review --queue review/ --pending   # or --show/--resolve/--export-labels
  # --show ID --html page.html renders the side-by-side review page
  # --image scan.jpg overrides the page's image path
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
  image is sent plus a REGION clause scoping the prompt to the
  crop's normalized bbox (stdlib header-parsed dims) — one doc
  per slip in multi-receipt photos, live-verified on a 2-up
  and pinned by a committed 2-crop e2e test.
  Pixel-level crop rendering is still future work.
- `glimmer`: offline extraction, wired (4-pass header/lines/dates/
  form over local Ollama `muse-glimmer`, ~18GB, zero cloud).
  Live-verified on S1 (all_correct, auto_accept). Segmentation is
  whole-image crop only; true offline SAM weights still future.
  `GlimmerReviewer` delegates to `triage()`.
- `tesseract`: system-A baseline; needs the `tesseract` binary with
  `tha+eng` data.

## Working agreements

- A half-hourly automation (:07/:37) shares this tree: keep diffs
  focused, run `make test` before finishing, and leave the tree green.
- Commit each finished, locally tested unit of work (`make test` green
  first); one focused change per commit. Push only when explicitly asked.
- Prove behavior changes by measurement (rule outcomes, extraction
  accuracy on fixtures/samples, e2e smoke), not by description.
- Keep live API spend trivial: tiny probes, mocked tests, no bulk
  batches without need.

## Sample + seed coverage (S1–S36)

Source photos live OUTSIDE the repo: `../rapee/docs/samples/S{n}.jpg`
(read-only, never copied in). Hand gold lives in
`src/ptl/eval/gold.py` (`SEEDS`, `fresh_seed`; `tests/fixtures.py`
is a re-export shim); transcription rule: zoom crops first, never
trust the AI draft or the overview read. `ptl labels` dumps gold
to a labels dir for `ptl eval` (gitignored, regenerable).

- Seeded (25): S1–S6, S7–S20, S21–S25. Pending: S29–S31
  trialed live (S30/S31 e2e, S29 Spark-only after 2 e2e
  timeouts) but NOT seeded — Thai prose needs a human zoom
  read per the transcription rule (open: S29 raw-date stamp
  choice + address line, S30 "N-" line prefix, S31 X40 qty).
  None are re-photos (all new sellers).
  Pending: S32–S36 trialed live (S32/S34 auto_accept,
  Foodland Laksi ABB sisters, 314.00/338.00 exact; S35
  needs_review on genuinely ambiguous 2-digit date
  1/11/69, tax/docno/lines/329.00 exact; S36 needs_review
  R14 unproven form, Wongnai POS tender mapped to
  qr_promptpay; S33 seller-less order chit missed by SAM
  under receipt AND bill concepts — measured recall gap,
  queued) but NOT seeded — human zoom reads still needed
  per the transcription rule. None are re-photos (S33/S35
  are the same visit T.4 but distinct chit vs ABB invoice,
  344.00 vs 329.00 — related, never dedup).
  (S20: MR. D.I.Y. ABB; 4th VAT-formula pin; anchorless 03-10-26
  stays ambiguous like S23. S24: Snowtee; 5th VAT-formula pin;
  "-0.0" discount; lowercase promptpay tender. S25: Zaab Only;
  S17 sister format, distinct sign; verbatim Coke variant.)
- Faded-thermal eval split (`data/faded.txt`): S5, S17.
- Sister slips (same shop/format — mirror the older seed's
  conventions): S13/S19 (Watsons), S16/S22 (7-Eleven 02304),
  S17/S25 (Isaan invoice, same phone 0819203944), S21/S28
  (Jamroenros, same company + phone 0955292838), S32/S34
  (Foodland Laksi ABB, same tax 0105515004549 + Free lines
  + SUBTOTAL-ALL/REG pair).
- Confirmed re-photos (zoom-verified, NOT independent seeds):
  S23/S26 (Oasis `1RC102569/008592`, 120.00), S22/S27
  (7-Eleven 02304 `R#0000240606P1`, 77.25) and S21/S28
  (Jamroenros, same second-stamp 13:13:27 + 99.00). Pinned as
  R10 dedup pairs in `tests/test_dedup.py`; S26/S27/S28 never
  get their own seeds.
- New formats in queue: S24 Snowtee (promptpay QR + VAT-pin
  candidate 2.29 on 35.00), S20 (unread).

## Known gaps (current)

150-receipt collection + 50 held-out eval labels (have 25
seeds + 3 dedup pins, 2 faded; harness runnable via ptl labels
+ ptl eval; baseline A 0/25 docs (grand 8/25, lines 0/25,
tax 9/25, dates 4/25 re-measured Nov 3, grand/lines reproduce),
single-prompt B 6/25 (grand/tax 23/25, lines 10/25, legal
9/25; S14/S24 timed out twice), full-pipeline C 7/25
C-context-verified, 25/25 scored (tax/grand/dates/form/
discount 25/25, subtotal/total 24/25, branch 23/25,
docno 24/25 with S11 the lone miss, legal 16/25, lines
15/25, vat 12/16, vatable 13/15; S1/S13/S19/S20/S24
fresh: v2/v3 hold in C, S24 docno exact on redo —
region variance was stochastic; S1 legal flips run to
run, demo smokes 57/67 green since the flake);
prompt v2
adds bare-#-15+-digit receipt-number rule (S13/S19 docno
were null, now exact gold live; S1 drift guard green,
LEDGER-MATCH holds); prompt v3 adds R-prefixed footer
docno rule (S20 null → exact live; S1/S24 guards exact,
S24 fills the missing C pred; S22 still found with char
confusion, no regression; S11 member-ID over-capture
clause failed live and was reverted — model limitation);
prompt v4 strips trailing branch tails from legal_name
(S1's สาขาที่ 00031; in-name digits kept per S18/S9;
S9's CO.,LTD punctuation miss is pre-existing; holds in
C context); live flake #3 (wholesale lines/payments/date/
docno drop, correctly blocked:R1,R5);
R# receipt repair in build (G/O/I→digits in R# + 10-digit
+ P1 runs, dropped R# restored; S22C/S5D recorded preds
→ gold exact, no other field moves; 25-seed docno guard);
printed-code strip (leading 6-digit product codes,
trailing EAN-13; raw kept; C lines 11→12, D 10→12;
25-seed line-name guard); subtotal alignment (prompt
said subtotals "are not line items" but gold transcribes
them flagged — clause fixed both backends, qty default
skips subtotal/header rows; S11 lines F1→1.0 both
systems, C/D lines 13/25); R4 fails vatable-without-vat
(live rehearsal auto-accepted an empty vat cell; zero
gold has the shape, S20's mirror still passes; seeds
hold 14/11); R11 branch floor 4→3 digits (S&P's genuine
สาขาที่ 291 false-flagged live; S30 flips to auto_accept,
seeds hold 14/11, S11's '3' still flags);
VAT recompute-in-prompt kept
deliberately through demo (transcribe-printed would flip S1
live to needs_review; revisit post-deadline); offline
Glimmer D 4/25 final (S1/S3/S6/S23; grand 25/25, tax
23/25, branch 18/25, legal 17/25, docno 17/25, form 16/25,
discount 24/25, dates 11/25, lines 13/25 (S19/S20
code-strip, S11 subtotal alignment); S5 accepted on
3rd attempt 6/12 fields — truncation is stochastic, not
deterministic; per-pass truncation tolerance shipped
(re-roll once, else empty section + source.truncated_passes,
proven by mocks); segmentation whole-image only);
pixel-level crop renderer (coordinate guidance
shipped + live-verified); demo video
(Nov 4 deadline); per-software export templates BLOCKED on
an accountant naming the target (spec §12 open question; our
CSV/XLSX already matches the §5 minimum). Queued
betterments: Glimmer date zoomed re-read or header-pass
fallback (retry recovered 0 captures — misses systematic,
not flaky); SAM order-chit recall (S33 missed under 6
concepts now — receipt/paper/bill + thermal
receipt/order ticket/sales slip; viewed the
frame: full-bleed paper with no background, so
no text-prompted box can fire — the fix is an
e2e whole-frame crop when SAM returns [], not
more concepts; still queued pre-deadline as a
spec-level behavior change to the no-receipt
path). Done: dates-pass empty retry + 2-digit
no-guess clause (S23 fixed, docs 3→4, dates 10→11);
per-pass truncation tolerance (S5 6/12 on 3rd attempt,
grand 25/25);
R10 seller-name fallback for tax-less
slips; tender map covers all 22 seeds' gold methods
(bank_transfer / Sbux-redeem / ShopeeFood / QPCB added; sweep
test pins future agreement); total inference (gross Σlines,
22/22 seeds recovered exactly); R11 Luhn gate (S15 NP/STID
false positive killed, S15 auto-accepts, Luhn-valid control
still flags); R10 content key for numberless/POS-less slips
(S21/S28 re-photo caught, zero collisions on 25 seeds;
live-verified end to end: S21 recorded, S28 excluded via
seen-store, exit 3);
Thai-digit canonicalisation for machine fields (R10 key
split fixed, prose untouched); blank machine-identity
fold ("" → null for tax/branch/docno/dates; D +12 fields:
tax 18→22, branch 12→17, docno 14→17, docs 3/25 hold).
Live flake 2026-10-31: Spark dropped lines+payments+date
on demo/sample.jpg AND emitted ~2728 junk keys in two
families (`can_claim_input_vat<U+xxxx>`, `currency<U+xxxx>`)
(decoding glitch; demo smoke 12/15 RED, e2e exit 2 by
design; next smoke GREEN 15/15 auto_accept; following
run 2/2 smokes read-timed-out server-side; API
recovered, smoke GREEN 15/15 auto_accept). Done:
unknown-key allowlist strip in build_document (flake
artifact 2740 keys → 12, zero junk, D re-score unchanged;
25-seed key-survival test pins the allowlist).
Queued hardening: S5 Glimmer retry. Done:
check_structure retry-on-junk (unknown top-level keys
are structure errors, capped at 5 + count; extractor
re-rolls once, keeps first structurally-clean attempt,
else first parseable — never a blind second; 25 seeds
still structure-clean). Done:
e2e/validate/export honor triage (smoke #40 flagged
needs_review on low non-money confidence yet exported
auto_accept — CSV status and validate exit now follow
triage on all three surfaces; flagged live doc replays
needs_review everywhere). Done:
e2e --review-queue enqueues flagged docs (struct-error +
triage non-auto_accept, R10 dups excluded not queued;
doc_id sanitizes "/" in receipt numbers; flagged live
doc → pending → `review --pending` proven). Done:
stdlib-only EXIF strip at ingest (APP1 Exif marker walk,
SOS-to-EOF verbatim; e2e routes adapters at a scrubbed
temp copy, provenance still names the phone photo;
demo/sample.jpg loses 1275 EXIF bytes, scan-identical;
smoke #46 caught the model echoing the temp filename
into source.image_uri — e2e now forces the original
basename when scrubbed (pinned); #44/#45 timeout pair
counted one miss, API recovered; #47 green live-verifies
the provenance fix, no tmp leak). Done:
recorded_run.txt re-captured from a green current-schema
run + freshness test in test_demo (schema keys,
auto_accept, row LEDGER-MATCH — the Oct-31 capture
showed the pre-strip Pillow note); data/labels regen
proven (25 files); repo visibility re-verified PUBLIC.
Done: stdlib-only XLSX export (to_xlsx was dead code
needing uninstalled openpyxl — rewritten with zipfile +
inline-string XML, wired by .xlsx extension on export
--out and e2e --csv, append refused with a clean error;
5 tests; macOS QuickLook renders the workbook with Thai
cells, screenshot-verified).
Done: e2e stamps source.image_hash (R10 exact-image leg
was dead — model leaves null; original-bytes hash,
strip-proof) + image leg scoped cross-run only (same
photo's crops share one hash; within-run collapse still
via content/doc keys; 2 tests + save/reload round-trip
proven).
Done: side-by-side review page (02 sec 14 — `ptl review
--show ID --html page.html` renders image + fields +
failed rules, stdlib-only, all values escaped; 3 tests;
bad_sum page screenshot-verified: banner, Thai fields,
red R1; --image override points the page at the real
scan (records carry bare basenames); trust beat
rendered through the real CLI, screenshot-verified).
Done: eval review cross-tab (05 sec 8 items 4-5 —
review rate, auto-accept accuracy, flag recall from the
same validate+triage, no API; self-eval on 25 seeds:
11 flagged, auto-accept 14/14 exact).
Done: baseline latency reporting (05 sec 8 item 6,
latency half — per-image seconds + totals in the
baseline summary, failures included; 2 tests; system A
measured 3.35s on sample.jpg; USD + THB estimates
landed below).
Done: validation-guided retry in production e2e (was
eval-only system C — best-of-N by failed count, early
break on auto_accept, claim derived per attempt, R10
still judged with the seen-store on the winner,
--attempts default 2; retry hardened: malformed
attempts skipped, all-malformed degrades to review;
5 tests; clean docs still cost 1 call).
Done: recorded_run.txt re-captured again (attempts +
stamped image_hash now in schema; freshness test pins
attempts).
Hygiene: doc-example e2e outputs (demo/out.json,
demo/ledger.csv) ignored; verified only .gitkeep is
tracked under data/labels and .env stays ignored.
Done: per-receipt usage on e2e (05 sec 8 item 6 —
calls/tokens/seconds per stage + wall elapsed in
every result; first measurement: 1 SAM + 1 Spark,
~7.3k tokens, 18.3s; 2 tests + recording re-captured
with usage pinned).
Done: USD cost estimates on e2e usage (05 sec 8 item 6,
cost half — per-leg estimated_usd + total from the
official pricing page, Spark $1.25/$4.25 per 1M,
SAM $2.50/1k images, local engines $0; unknown models
yield None legs and no total, never a silent partial;
7 tests; smoke #72 receipt reprices at ~$0.018).
Done: partial-capture detection + enforcement (05 sec 5
stage 1 — box_cut_by_frame flags SAM boxes running into
the frame edge at 1% margin, whole-frame fallback boxes
exempt; e2e extracts partial crops for the reviewer but
forces needs_review + retake note + queue slot, never
auto_accept; reverses the old "no signal in boxes" note,
recorded in the sam31 docstring; 7 tests failing-first
proven; smoke #74 green 15/15 with partial False on the
live whole-frame box; #73 was a stochastic wholesale
drop, correctly blocked:R1, recovered next run).
Done: THB cost figures on e2e usage (05 sec 8 item 6
closed — per-leg estimated_thb + total from the USD
estimate at a pinned 33.65 THB/USD, dated 2026-11-01
mid-market consensus, None-safe like the USD legs;
4 tests failing-first proven; smoke #75 reprices the
receipt at ฿0.61 live). DEMO.md test count refreshed
(403 → 421).
Done: R11 correctness (02 sec 7 + sec 10 — the email
blocklist held a bare "-" that flagged every hyphenated
address (proven live-shape FP) and missed spec-listed
*@invalid (proven FN): dropped "-", added "invalid";
card scan extended from address/discarded-text to
payment card_mask/method_raw/external_ref, where PANs
actually surface — masked XXXX shapes can't match,
PromptPay numeric refs fail the Luhn gate; 5 tests incl
a 25-seed sweep holding {S11, S3}; smoke #76 green
15/15 auto_accept at ฿0.70; DEMO.md count → 426).
Verification run: full DEMO.md rehearsal, every beat
executed as scripted — ingest, live e2e + diff beat
(LEDGER-MATCH), 426 green, s1 validate/export,
bad_sum exit 2 + queued R1, review HTML renders,
demo/s1.json == S1 seed exactly; 01-doc-model diff
clean for OCR scope (issuing §§5-6/9 out of scope;
supply_type/vat_flag/vat_mode already in schema);
POS normaliser wired (tesseract) + pinned; no code
change warranted, all gaps human/spec-blocked;
smoke #77 green 15/15 auto_accept at ฿0.68; DEMO.md
smoke stats refreshed (57/67 → 65/77 + #73 miss).
Verification run: 7-doc personal coverage complete
(00 product plan: no OCR action; 04 invoicing flow
explicitly out of OCR scope, prior judgment stands);
compliance re-verified (18 commits, oldest Oct 28;
no key-shaped strings in tree; .env + demo outputs
ignored); offline beats hold. Smoke #78 went red:
0 lines, blocked:R1,R5 exit 2, both attempts spewing
~20K output tokens (฿6.14, 9x norm) + a ~600s hung
HTTP call inside the 713s elapsed — pipeline held,
never posted. #79 retry self-terminated after 1207s:
both attempts returned `{}`, structurally excluded,
exit 3, 0 rows, SAM-only ฿0.08 (hung calls unbilled) —
third API-flake variant, correctly contained.
Done: Spark max_output_tokens=8000 (flake spend
guard — 4x headroom over the ~2K norm, truncation
falls into the existing re-roll path; None disables;
2 tests failing-first proven; smoke #80 green 15/15
auto_accept at ฿0.58 with 2026 out-tokens, proving
the param live; DEMO.md 66/80 + count → 427).
Done: 25-seed triage-split pin (test-only — the claimed
14-auto/11-flag split had no test; measured live, both
directions pinned, sensitivity proven by flip/fail;
stale __pycache__ bit once during the flip, cleared;
smoke #81 green 15/15 auto_accept at ฿0.65; DEMO.md
67/81, 8K cap in defenses, count → 428).
Offline re-probe: muse-glimmer serves (31s incl load);
System D on demo/sample.jpg completes, grand 4500
exact, needs_review on dates.issue_date alone — the
known systematic dates gap, unchanged; offline path
real, dates fix stays queued (rabbit hole); smoke
#82 green 15/15 auto_accept at ฿0.73; DEMO.md 68/82.
Done: README quickstart made runnable (eval line
cited nonexistent eval/preds.json + faded.txt,
baseline cited nonexistent samples/, review cited
empty review/ — now the real labels/baseline/eval
chain with data/faded.txt + seeded demo/review/,
each beat executed); chain exposed tesseract
stdout decoded strict — sandboxed /tmp runs died
UnicodeDecodeError, now errors="replace" (1-word
robustness + pinning test, failing-first proven;
in-workspace OCR verified: Thai text, 3.2s, S1
grand exact via regex); temp copy deleted, tree
clean of pre-event bytes; smoke #83 green 15/15
auto_accept at ฿0.92; DEMO.md 69/83, count → 429.
Verification run: data/labels holds .gitkeep +
fresh ignored 25-label regen (no hygiene issue);
full-system-C re-eval considered and declined
(single stochastic re-run of a headline number
pre-deadline = noise-chasing risk; committed
numbers stand as measured); no code change
warranted, all gaps human/spec-blocked; smoke
#84 green 15/15 auto_accept at ฿0.64; DEMO.md
70/84.
Done: recorded_run.txt re-captured (no-network
fallback predated cost reporting — had attempts +
partial but no estimated_usd/thb; freshness test
now pins partial + the three cost keys, failed
pre-capture, green after; smoke #85 green 15/15
auto_accept at ฿0.65 sourced the capture; DEMO.md
71/85).
Verification run: repo visibility re-checked PUBLIC
via gh; hackathon notification eml is the Oct-26
kickoff blast (dates confirmed, nothing new); no
code change warranted; smoke #86 green 15/15
auto_accept — adapter re-roll fired live (2 calls,
1 attempt, first response unusable, ฿1.14), final
reads exact; DEMO.md 72/86.
Verification run: corrections→labels→eval loop
proven live through the real CLI on a scratch
queue copy (resolve bad_sum with s1.json →
exported LABELS-MATCH → eval consumes it; demo
queue untouched); no code change warranted;
smoke #87 green 15/15 auto_accept at ฿0.60;
DEMO.md 73/87.
Verification run: submission rules re-mined from
the saved guide (public repo + video link +
contributor list, one Representative submission;
Indie $400K/150/100/75/50/25K confirmed, $1M is
the two-track total; Glimmer-on-Ollama qualifies
structurally for the $10K open-weight bonus) —
all remaining pieces are the user's; no code
change warranted; smoke #88 green 15/15
auto_accept at ฿0.65; DEMO.md 74/88.
Verification run: offline demo beats
re-verified post-R11-changes (s1 exit 0, bad_sum
exit 2, export row, queued bad_sum, review HTML
7738 bytes deterministic); packaging sane (zero
runtime deps); no code change warranted; smoke
#89 green 15/15 auto_accept at ฿0.63; DEMO.md
75/89.
Verification run: XLSX export proven live via
the real CLI (valid zip, Thai bytes present);
no code change warranted; smoke #90 green
15/15 auto_accept at ฿0.64; DEMO.md 76/90.
Verification run: dedup append cycle proven
live (exit 0 → duplicate note → exit 3, no
double-append); no code change warranted;
smoke #91 green 15/15 auto_accept — re-roll
fired again (2 calls, both ~5K out-tokens,
฿1.96), final exact; 8K cap headroom
confirmed necessary, untouched; DEMO.md 77/91.
Verification run: tree hygiene swept (5 known
untracked, no strays, no pre-event bytes);
no code change warranted; smoke #92 green
15/15 auto_accept, 1 call, ฿0.71; DEMO.md 78/92.
Multi-receipt probe: synthetic S1+S2 2-up live —
2 crops, 2 docs, both rows exact (CP AXTRA 89.00
+ PTT 45.00), exit 2. Both boxes touch exact
frame edges (full-bleed source photos) so the
partial heuristic fired on complete slips:
geometry cannot separate tight-complete from
cut-off (exact-edge margin would fire too).
Conservative flag kept — a glance beats a wrong
row; text-aware partial detection (extractor-
reported truncation) queued post-deadline. No
code change; smoke #93 green 15/15 auto_accept
at ฿0.67; DEMO.md 79/93.
Faded probe: live S5 (known-risk segment)
reads all fields exact vs gold, auto_accept,
1 attempt, ฿0.67 — faded path healthy on
current code; no code change; smoke #94
green 15/15 auto_accept at ฿0.78; DEMO.md
80/94.
Faded probe 2: live S17 (faded invoice)
needs_review on R14, matching gold triage —
money exact, misses confined to faded Thai
prose (legal suffix dropped, 1/4 lines
misread); flags-instead-of-guessing holds on
the hard segment, no code change; smoke #95
green 15/15 auto_accept at ฿0.68; DEMO.md
81/95.
Done: .env.example for fresh clones (key
discovery was word-of-mouth; .env.* glob
would swallow it, so a `!.env.example`
exception + a pinning test that asserts the
example exists, names MODEL_API_KEY, stays
committable while .env stays ignored;
failing-first proven via commented exception;
smoke #96 green 15/15 auto_accept at ฿1.98
(re-roll fired); DEMO.md 82/96, count → 430).
Done: reasoning_tokens in usage stats (raw-
response probe: status completed, no
truncation — 8K cap safe; ~half of output
is reasoning trace (1197/2381), so chatty
calls are verbosity variance, not cap-edge;
record_call + e2e snapshots carry the split
for future forensics; 2 tests failing-first
proven; smoke #97 green 15/15 auto_accept
at ฿0.61 with 957/2200 live; DEMO.md 83/97,
count → 431).
S33 probe: 3 more concepts miss (6 total);
frame viewed — full-bleed paper, no
background, so text-prompted SAM cannot
fire; whole-frame fallback is the confirmed
design, still queued pre-deadline; no code
change; smoke #98 green 15/15 auto_accept
at ฿0.61; DEMO.md 84/98.
Verification run: eval splits correctly
staged-empty (no dead CLI flags; 50-held-out
awaits human collection); no code change
warranted; smoke #99 green 15/15 auto_accept
via validation retry (attempt 1 failed, 3
calls, 18.4K out all under cap, ฿3.34) —
robustness priced, final exact; DEMO.md 85/99.
Done: label-contract truth (schema line_item
lacked description_raw while seeds+template+
build all carry it — added, plus a parity test
asserting every seed key at top/line/pay/party/
totals exists in the schema, failing-first
proven; COLLECTION.md refreshed: 25 seeds in
gold.py, ABB have 25, S17 faded-listed;
smoke #100 green 15/15 auto_accept at ฿0.68;
DEMO.md 86/100, count → 432).
Done: parity test extended to label.template
(blank label humans copy now pinned against
the schema too; fails on the pre-fix schema,
passes after; no new test count); smoke #101
green 15/15 auto_accept via retry (4 calls,
26.7K out all within cap, ฿4.74) — re-roll
rate up recently (model variance, pipeline
absorbing, no defect); DEMO.md 87/101.
Verification run: cross-run R10 proven live
via --seen (run 1 auto_accept, run 2 excluded
duplicate exit 3, 0 rows); no code change
warranted; smoke #102 green 15/15 auto_accept
at ฿0.77; DEMO.md 88/102.
Verification run: 03-vs-ours re-diffed after
the description_raw fix — every ref key covered
at all levels (the fix converged us: ref had the
key all along); extras exactly the deliberate
trio (status, rounding_adjustment,
is_category_subtotal); no code change warranted;
smoke #103 green 15/15 auto_accept via retry
at ฿3.35; DEMO.md 89/103.
Verification run: compliance re-checked
pre-deadline — commits Oct 28+ (window
clean), repo PUBLIC, .env untracked +
ignored, key-scan hits all fake test
fixtures; no code change warranted; smoke
#104 green 15/15 auto_accept via retry
at ฿2.68; DEMO.md 90/104.
Verification run: full offline DEMO.md
rehearsal — ingest, 432 green, s1 exit 0
all-pass, export row, bad_sum exit 2 R1,
review pending, review HTML deterministic
7738 bytes; no code change warranted;
smoke #105 green 15/15 auto_accept clean
first attempt at ฿0.73; DEMO.md 91/105.
Verification run: labels→eval self-chain
healthy post-label-contract — 25/25 docs
exact, every field 1.0, faded 2/2, cross-tab
11 flagged/14 auto at accuracy 1.0; no code
change warranted; smoke #106 green 15/15
auto_accept clean first attempt at ฿0.68;
DEMO.md 92/106.
Done: scorer folds Co.,Ltd. variants (05
sec 8 metric table says legal name is
"exact after normalisation (whitespace,
Co.,Ltd. variants)" — normalise_legal only
collapsed whitespace, so S9's CO..LTD vs
CO.,LTD read scored a miss: suffix spellings,
print misprints, and spelled-out "company
limited" now fold to "co ltd"; Thai legal
forms + stem case untouched; 4 tests
failing-first proven, 25/25 self-match
holds; committed C/D legal counts were
measured under the strict scorer and stand
as conservative lower bounds, no re-run;
smoke #107 green 15/15 auto_accept clean
first attempt at ฿0.72; DEMO.md 93/107,
count → 436).
Verification run: 02 edge-cases §§4-15
re-diffed section by section — all handled
(line traps, payments≠totals, open tender
enum, position-agnostic card scan, 3-level
naming, POS drift, noise blocklist incl
*@invalid verified live in EMAIL_BLOCKLIST,
R1-R8 ⊂ R1-R14, review queue + side-by-
side page); remainder queued with reason
(PII mask, pixel quality gate, QR decode)
or human-blocked (§15 collection); no code
change warranted; smoke #108 green 15/15
auto_accept via retry at ฿1.31; DEMO.md
94/108.
Measurement run: baseline A re-run
offline on all 25 seeds under the folded
scorer — 0/25 docs, grand 8/25, lines
0/25, legal 0/25 (regex emits no names,
nothing to fold): committed A numbers
stand exactly, scorer change moves
nothing; env note: tesseract subprocess
cannot open /tmp images under this
sandbox (leptonica fopen fails, symlinks
or copies alike) — run OCR batches from
an in-workspace scratch dir and delete
it after (done, tree clean); no code
change warranted; smoke #109 green 15/15
auto_accept clean first attempt at ฿0.68;
DEMO.md 95/109.
Verification run: 05 §§5-7 pipeline
stages re-diffed — ingest/segment/
extract/validate/export all live as
specced (source.image_quality in schema,
R12 reads real per-field field_confidence);
remainder queued with reason (pixel
de-skew/enhance/metrics, targeted field
re-read, Thai explanations, polygon
highlight) or human-blocked (§7 dataset
rules); no code change warranted; smoke
#110 green 15/15 auto_accept clean first
attempt at ฿0.74; DEMO.md 96/110.
Offline re-probe: System D on the demo
sample completes (158s), grand 4500 exact,
dates section empty → needs_review R13 —
same known systematic dates gap as #82,
DEMO.md close claim holds; dates fix stays
queued; no code change warranted; smoke
#111 green 15/15 auto_accept clean first
attempt at ฿2.08; DEMO.md 97/111.
Verification run: 01 doc-model re-diffed
in full — every OCR-scope key verified
live in schema (doc types, ABB rule,
satang/bp/formulas, supply_type, vat_flag,
vat_mode, counterparty-as-buyer,
references_document_id, payment events);
issuing-side §§3/5/6/9 correctly out of
scope, prior judgment stands; no code
change warranted; smoke #112 green 15/15
auto_accept via retry at ฿3.72; DEMO.md
98/112.
Verification run: CLI surfaces re-proven
post-label-contract through the real CLI
(XLSX valid zip + Thai bytes + 45.00,
dedup exit 0 → note → exit 3 with no
double-append, corrections resolve →
export-labels LABELS-MATCH on a scratch
queue, demo queue untouched); no code
change warranted; smoke #113 green 15/15
auto_accept clean first attempt at ฿2.00;
DEMO.md 99/113.
Faded probe 3: live S5 auto_accept, money/
tax/dates/lines all exact, lone miss is
legal "CP ALL, 7-Eleven" vs gold "CP ALL"
(brand appended to the entity — stochastic
prose variance, exact at #94; no prompt
churn on n=1, watch for a pattern); no
code change warranted; smoke #114 green
15/15 auto_accept clean first attempt at
฿0.65; DEMO.md 100/114.
Done: prompt v5 legal-brand separation
(S5 brand-append replicated 2/2, pattern
not noise: legal bullet gains "never append
the brand or store name (CP ALL, not 'CP
ALL, 7-Eleven')", mirrored in Glimmer
header prompt; 1 pin test failing-first
proven; live S5 flips to CP ALL all-
correct, S1 guard holds; smoke #115 green
15/15 auto_accept clean first attempt at
฿0.60; DEMO.md 101/115, count → 437).
Verification run: v5 regression check on
S6 (second legal/brand split) — legal
exact, all_correct, auto_accept, no over-
stripping; v5 generalizes; no code change
warranted; smoke #116 green 15/15
auto_accept clean first attempt at ฿0.66;
DEMO.md 102/116.
Verification run: 04 re-read in full —
issuing/PSP flow, §7 explicitly lists OCR
as out of scope (zero OCR-actionable
items, prior judgment stands); data-model
overlaps already mirrored; tree hygiene
swept (known 6 untracked, no strays); no
code change warranted; smoke #117 green
15/15 auto_accept clean first attempt at
฿0.57; DEMO.md 103/117.
Faded probe 4: live S17 under v5 —
needs_review matching gold triage, money
exact, misses confined to faded Thai prose
(legal suffix + lines as at #95, pre-v5
behavior unchanged, no v5 regression); no
code change warranted; smoke #118 green
15/15 auto_accept clean first attempt at
฿0.63; DEMO.md 104/118.
Verification run: compliance re-checked
(PUBLIC, commits Oct 28+, .env untracked,
key-scan hits only the gitignored .env);
no code change warranted; smoke #119
green 15/15 auto_accept clean first
attempt at ฿0.70; DEMO.md 105/119.
Verification run: S5 v5 fix durable 2/2
post-v5 (CP ALL all-correct auto_accept);
no code change warranted; smoke #120
green 15/15 auto_accept clean first
attempt at ฿0.73; DEMO.md 106/120.
Verification run: 00 + README re-read —
product/market/phasing, OCR is Phase 4
"fallback not headline" but 05 is the
explicit build brief; the three bite-
points all live in code; no OCR action,
prior judgment stands; no code change
warranted; smoke #121 green 15/15
auto_accept clean first attempt at ฿0.64;
DEMO.md 107/121.
Live probe: S20 all fields exact (legal
fold scores, docno R000500494 exact, no
v5 over-strip of "(BANGKOK)"),
needs_review matching gold triage (R13;
gold adds R7 on its ambiguous-era marker,
same outcome); no code change warranted;
smoke #122 green 15/15 auto_accept clean
first attempt at ฿0.79; DEMO.md 108/122.
Live probe: S9 legal verbatim exact
(2022 + CO..LTD kept), lines 1.0, lone
miss branch null vs 71498 (existing
transcribe-when-printed clause disobeyed
once; null-branch invisible to validation
so retry cannot fix — n=1, watch for a
replicate before touching the clause); no
code change warranted; smoke #123 green
15/15 auto_accept clean first attempt at
฿0.63; DEMO.md 109/123.
Done: prompt v6 branch-outlet clause (S9
branch-null replicated 2/2; slip viewed:
71498 prints as footer "Restaurant ID",
no branch cue — clause transcribes
Restaurant/Store/Outlet IDs as branch_code
when no branch-labeled number prints,
mirrored in Glimmer header; 1 pin test
failing-first proven; live S9 flips null
→ 71498 all-correct, S1 guard holds
00031 not 2083; smoke #124 green 15/15
auto_accept via retry at ฿2.71; DEMO.md
110/124, count → 438).
Verification run: v6 regression check on
stamp-heavy S2 — branch 1681 exact (no
over-fire on stamp soup), docno null
exact (no assembly), all_correct
auto_accept; v6 generalizes; no code
change warranted; smoke #125 green 15/15
auto_accept clean first attempt at ฿0.68;
DEMO.md 111/125.
Verification run: S9 v6 fix durable 2/2
post-v6 (71498 all-correct auto_accept);
no code change warranted; smoke #126
green 15/15 auto_accept clean first
attempt at ฿0.61; DEMO.md 112/126.
Live probe: S13 auto_accept, docno bare-#
exact; 3 scorer misses dissected, none
actionable — legal case (slip prints
lowercase watsons, gold verbatim-right,
model normalized once; R10 keys already
lowercased so dedup immune, scorer stays
strict, n=1 watch), VAT 327-vs-328
(recompute policy vs printed 3.28, R3 ±1
passes both, recorded post-deadline
revisit), lines @/O single-char confusion;
no code change warranted; smoke #127
green 15/15 auto_accept clean first
attempt at ฿0.57; DEMO.md 113/127.
Live probe: S19 auto_accept, legal
lowercase exact (S13 case confirmed n=1
variance, watch closed), date exact; lines
0.0 on #-as-W glyph confusion both lines
(qty/totals exact, R1 passes; n=1 watch,
no clause for glyph pairs); VAT 327-vs-
328 same Watsons-POS printed shape as
S13, R3 ±1 passes both, policy stands; no
code change warranted; smoke #128 green
15/15 auto_accept clean first attempt at
฿0.62; DEMO.md 114/128.
Live probe: S22 auto_accept, legal CP ALL
exact (v5 holds), lines 1.0, lone miss
docno digit-drop in the R# run (...4006..
vs ...40606..; model misread, not the R#
repair; exact-copy clause already demands
it, n=1 watch); no code change warranted;
smoke #129 green 15/15 auto_accept clean
first attempt at ฿0.72; DEMO.md 115/129.
Live probe: S15 auto_accept, Luhn gate
holds live (no R11 FP); misses dissected —
legal "Tops Esplanade" vs gold Tops (v5-
class mall-name append, n=1 watch), lines
Thai model-normalized to dictionary words
vs gold verbatim non-words (slip viewed;
verbatim-vs-normalize convention question
+ possible gold typo shapes — flagged for
human Thai adjudication, gold untouched);
no code change warranted. Smoke #130 RED:
wholesale dates/lines/payments/docno drop
both attempts (R1+R13 → needs_review exit
2, 25.7K out/4 calls all within 8K cap,
฿4.61) — 3rd instance of the known flake
class, pipeline held never posted, not
v5/v6-caused (drops predate them); counted
as miss, recovery rides next run; DEMO.md
115/130.
Recovery run (48h window now open —
demo-critical scope only): smoke #131
green 15/15 auto_accept clean first
attempt at ฿2.08, #130 confirmed
stochastic; no code change warranted;
no peripheral probes this run; DEMO.md
116/131.
Verification run (48h demo-critical
scope): smoke #132 green 15/15
auto_accept clean first attempt at ฿0.64,
2nd consecutive green after #130; no
code change warranted; DEMO.md 117/132.
Verification run (48h demo-critical
scope): smoke #133 green 15/15
auto_accept clean first attempt at ฿2.00,
3rd straight green after #130; no code
change warranted; DEMO.md 118/133.
Verification run (48h demo-critical
scope): smoke #134 green 15/15
auto_accept clean first attempt at ฿0.91,
4th straight green after #130; no code
change warranted; DEMO.md 119/134.
Verification run (48h demo-critical
scope): smoke #135 green 15/15
auto_accept clean first attempt at ฿0.65,
5th straight green after #130; no code
change warranted; DEMO.md 120/135.
Verification run (48h demo-critical
scope): smoke #136 green 15/15
auto_accept clean first attempt at ฿0.75,
6th straight green after #130; no code
change warranted; DEMO.md 121/136.
Verification run (48h demo-critical
scope): smoke #137 green 15/15
auto_accept clean first attempt at ฿1.17,
7th straight green after #130; no code
change warranted; DEMO.md 122/137.
Verification run (48h demo-critical
scope): smoke #138 green 15/15
auto_accept clean first attempt at ฿0.65,
8th straight green after #130; no code
change warranted; DEMO.md 123/138.
Verification run (48h demo-critical
scope): smoke #139 green 15/15
auto_accept clean first attempt at ฿1.25,
9th straight green after #130; no code
change warranted; DEMO.md 124/139.
Verification run (48h demo-critical
scope): smoke #140 green 15/15
auto_accept clean first attempt at ฿0.69,
10th straight green after #130; no code
change warranted; DEMO.md 125/140.
Verification run (48h demo-critical
scope): smoke #141 green 15/15
auto_accept clean first attempt at ฿0.68,
11th straight green after #130; no code
change warranted; DEMO.md 126/141.
Verification run (48h demo-critical
scope): smoke #142 green 15/15
auto_accept clean first attempt at ฿0.71,
12th straight green after #130; no code
change warranted; DEMO.md 127/142.
Verification run (48h demo-critical
scope): smoke #143 green 15/15
auto_accept clean first attempt at ฿1.28,
13th straight green after #130; no code
change warranted; DEMO.md 128/143.
Verification run (48h demo-critical
scope): smoke #144 green 15/15
auto_accept clean first attempt at ฿0.68,
14th straight green after #130; no code
change warranted; DEMO.md 129/144.
Verification run (48h demo-critical
scope): smoke #145 green 15/15
auto_accept clean first attempt at ฿2.01,
15th straight green after #130; no code
change warranted; DEMO.md 130/145.
Verification run (48h demo-critical
scope): smoke #146 green 15/15
auto_accept clean first attempt at ฿2.08,
16th straight green after #130; no code
change warranted; DEMO.md 131/146.
PII run (02 sec 12, user-ordered): scrub_doc ships in
ingest.py and wires into e2e post-extract (regex-masks
discarded_text/descriptions/method_raw, drops issuer.phone,
nulls real issuer.email, keeps R11 placeholders); CARD_RE
gains full-PAN + X-mask alts, PHONE_RE mid-alphanumeric
guard; no-names clause pinned in Spark + Glimmer prompts;
gold sweep proves zero scored movement on 25 seeds;
README eval filled (A tax 9/25 dates 4/25 re-measured,
B dates n/m footnoted); smoke #147 green auto_accept
first attempt at ฿0.64, 17th straight; 444 green.
Takes run (user-ordered, demo-critical): all three screen
takes RECORDED via VHS + frame-verified — take1_2up.mp4
(158 s; full-res S1+S2 80px-margin composite beats the 1%
partial tripwire, both rows auto_accept 45.00+89.00,
฿2.68), take2_trust.mp4 (11 s; R1 exit 2 → pending →
trust.html 7684 B), take3_glimmer.mp4 (161 s; system d
MODEL_API_KEY unset, 1 pred 0 errors, 4500/legal/tax
exact, localhost-only adapter). Tapes + TAKES.md in
demo/video/submit/ (ignored workbench). VHS drops Thai
combining marks font-independently — Thai close-ups must
be stills, never VHS frames. No repo-tree change; 444
green; committed 95c3cf8 + pushed, tree clean.
Sample + stills run (48h demo-critical): recompressed
demo/sample.jpg (2.4MB→483KB, same 1755×3465) smokes
clean — auto_accept, 4500 + exact legal, only diff vs
expected.csv is the source_image_ref provenance tag
(sample.jpg vs s1.jpg), all 15 substantive columns
identical: recompression BENIGN, keep the file. Smoke
#148 green at ฿3.49, 18th straight. Focused change:
scripted SAM-overlay still (stills/make_overlay.py →
overlay_2up.png, 2 green boxes + row chips, pixel-
verified) for PLAN shot 5; VHS tapes + TAKES.md updated.
444 green; sample.jpg + log left uncommitted (not mine
to commit).
Shot-5 run (48h demo-critical, peer assembling): v2
verified compliant — 2:53 (< 3:00 hard limit), 1080p
H.264 + AAC 48kHz, loudness −14.2 LUFS on target;
eval card numbers match README exactly incl. Glimmer
offline legend. Only hole was shot 5 (build.py skips
it until shots/05_twoup.mp4 exists): cut 13.4 s from
take1 (command + usage/CSV, both auto_accept) and
delivered the exact handoff file, join frame-checked.
Recorded-fixture smoke green (s1 validate 0, export
exact, bad_sum pending, zero API spend). Sample.jpg
mystery solved by peer commit d7cd254 (PII redaction).
444 green; tree clean at 619cc32.
Photo-bridge run (48h demo-critical): v3 is a v2
re-encode (identical 173.301729 s timeline, no shot 5;
specs still pass, captions + PII-redacted receipt
confirmed in frames) — peer renamed the handoff to
shots/05_twoup_final.mp4 and wants a REAL phone photo,
deliberately rejecting composites. Shipped the bridge:
SHOOT_05.md (framing rules from the 1% partial lesson)
+ render_05.sh (live e2e + VHS + measured auto-cut to
the exact filename; logic dry-validated to identical
13.4 s). BLOCKED on user shooting real_2up.jpg.
Timing warning logged: 173.3 s + shot 5 ≈ 186 s needs
~7 s trimmed elsewhere for the 3:00 hard limit.
Recorded smoke green, zero API. 444 green.
DEMO.md freshness run (48h demo-critical): executed every
documented command — all green (ingest pass-through on
redacted sample, s1 validate 0, export row exact, pending
bad_sum). Fixed 3 stales: 438→444 tests, 131/146→133/148
smokes, EXIF honesty note (live ingest shows pass-through
post-redaction; strip proven by unit test + recording).
Recording deliberately NOT re-cut: the freshness test
requires exif_stripped=true and the old capture is a
truthful record of its run. Video TODO now names v3 +
pending shot 5/upload. No photo yet, no v4. 444 green.
Live-verify run (48h demo-critical): smoke #149 green —
auto_accept first attempt, 4500, only source_image_ref
differs, ฿0.65/25.5s, 19th straight; redacted sample
demos clean twice. Fallback claim proven structurally:
zero network imports in pipeline/review/schema/score/
money — only adapters/ touch sockets (glimmer local,
spark/sam31 cloud). README quickstart audited line by
line, all accurate. No code change warranted; still
blocked on user photo + peer v4. 444 green.
Public-access run (48h demo-critical): repo proven PUBLIC
two independent ways — unauthenticated GitHub API says
private:false (main, pushed Nov 3), and credential-less
git ls-remote resolves HEAD 619cc32. Disqualification
risk closed. Recorded smoke green (s1 0, bad_sum 2,
export byte-matches expected.csv), zero API. No code
change warranted; still blocked on photo + v4. 444 green.
Hygiene run (48h demo-critical): secrets scan clean —
zero key patterns in tracked files (only CSS mask-image
false hits in the hackathon .mhtml), .env gitignored.
New-work-only holds: all commit dates Oct 28/29/31 +
Nov 3, inside the window. Recorded smoke green (s1 0,
bad_sum 2), zero API. No code change warranted; still
blocked on photo + v4. 444 green.
Integrity run (48h demo-critical): v3 full-decode clean
(ffmpeg error-scan exit 0, zero bad frames — upload-safe;
22.8 MB mp4). Recorded smoke green (s1 0, bad_sum 2),
zero API. No code change warranted; still blocked on
photo + v4. 444 green.
Smoke-150 run (48h demo-critical): live e2e green —
auto_accept first attempt, 4500, only source_image_ref
differs, ฿0.64/25.1s, 20th straight. No code change
warranted; still blocked on photo + v4. 444 green.
XLSX run (48h demo-critical): accountant surface
re-verified offline — export is a valid zip workbook
with sheet1.xml carrying the legal name + 45.00.
Recorded smoke green (s1 0, bad_sum 2), zero API. No
code change warranted; still blocked on photo + v4.
444 green.

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
