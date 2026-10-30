# Phone-to-ledger — dataset collection protocol

Goal: **150 real receipts — 100 dev + 50 held-out test.** The seed set
(S1–S6, ABB thermal slips) already exists as code fixtures in
`tests/fixtures.py`; this protocol covers the other ~144, especially the
document types the seed set has **none** of.

## 1. What to collect

Stratify deliberately. Quotas below are minimums, not exact splits.

| Axis | Buckets (minimum each) |
|---|---|
| Document type | ABB thermal (have 6), **full-form A4 tax invoice (≥15)**, **handwritten bill (≥15)**, credit note (≥5) |
| Condition | clean, **faded thermal (10–15 of the 50 test)**, crumpled/creased, **multi-receipt photo (≥10 overall)** |
| Money shapes | service charge + VAT stack, zero-rated/exempt lines, foreign currency, rounding adjustment, split payment |
| Language | Thai-only, Thai+English mix, English-heavy (US-origin POS) |

Still missing entirely (05 §3): full-form A4, handwritten, credit note,
multi-page invoice, service charge + VAT, zero-rated/exempt lines, foreign
currency. Prioritise these over more clean ABB slips.

## 2. Held-out discipline (read before photographing)

1. **Freeze the 50 before any prompt tuning.** Once frozen, never look at
   test failures while iterating. Suggested freeze:
   `sha256sum data/test/* > data/test/FROZEN.manifest`, then treat
   `data/test/` as read-only.
2. **No merchant leakage.** A merchant + branch layout in dev must not
   reappear in test (a Cafe Amazon slip in dev makes one in test easy).
3. **Faded thermal needs 10–15 of the 50.** S5-style faded, creased slips
   are what real users photograph; report accuracy on them separately.
   Seed judgment (contact sheet + zoomed crops, 2026-10-30): only S5 of
   S1–S20 is truly faded print; S8/S11/S14/S15/S17/S19 were examined and
   are dark print on gray/creased paper, not faded. S21–S23 examined
   2026-10-30 (full views + S22 zooms): legible gray print, none
   S5-level faded. Recorded in `data/faded.txt`; append test IDs as
   the 150 grow.
4. **Include multi-receipt photos** so segmentation is tested end to end.
5. **Double-label ~20 receipts** (second file
   `labels/<id>.labeler-b.json`). Fields humans disagree on cannot be
   scored strictly.

## 3. Shot checklist (per photo)

- [ ] Whole slip in frame — nothing cut off (a cut-off slip is `partial`
      and must never be extracted as complete)
- [ ] Paper as flat as possible; un-curl thermal rolls
- [ ] Slip fills the frame; camera parallel to the paper (low skew)
- [ ] Even light, no flash glare on thermal paper, no shadows over text
- [ ] In focus — amount lines and the tax ID must be pixel-readable
- [ ] Timestamps, QR codes, and footers visible (print time, survey QRs,
      portal notices are all traps the extractor must handle)
- [ ] Photograph bad slips **as they are** — faded, creased, stained.
      Do not retouch, enhance, or reprint.
- [ ] Got the shop's permission (see §5).

## 4. Layout and naming

```
data/
  dev/                  dev photos:   dev-001.jpg, dev-002.jpg, ...
  test/                 test photos:  test-001.jpg, ... (frozen, read-only)
  labels/               ground truth: dev-001.json, test-001.json, ...
  faded.txt             one doc id per line (the faded-thermal subset)
  COLLECTION.md         this file
  label.template.json   blank label skeleton (copy, never fill in place)
```

Photo and label share the id stem. Any image format the segmenter
accepts is fine; keep originals (EXIF location is stripped at ingest).

## 5. PII and permission (PDPA)

- Get the shop's permission before collecting receipts.
- Mask PII at ingestion, not at display (`ptl.pipeline.ingest.mask_pii`;
  cashier/customer names, phones, member numbers, card digits).
- Placeholder emails (`*@noemail.*`) are POS artefacts, never addresses.

## 6. Labelling

1. Copy `data/label.template.json` to `data/labels/<id>.json` and fill it.
   Amounts are **integer satang**, VAT rate is basis points (700 = 7%).
2. Keep raw strings next to normalised values (`raw_date_string`,
   `description_raw`, `method_raw`).
3. Dates: a 4-digit year ≥ 2500 is BE (subtract 543). A 2-digit year is
   **ambiguous without a corroborating anchor** (e.g. a TID embedding the
   AD date) — leave `issue_date` null, set `detected_era: "ambiguous"`,
   never guess. Loyalty expiry and print time are not the document date.
4. VAT: always recompute (`vat = round(total × 7 / 107)`); never trust the
   printed figure. Record what the slip shows in `vat_amount` and the
   recomputation in `vat_amount_computed`.
5. Lines: modifiers attach to `parent_line_number`; trailing `V`/`N`/`E`
   is a `vat_flag`, not part of the number; `X4`-style counts are
   `quantity_source: "embedded_in_name"`; section headers and category
   subtotals are flagged, never summed.
6. Payments are **not** totals: total-labelled rows → `totals`, tender
   rows (QR, card, voucher) → `payments[]`, which must sum to the total.
7. Classify every QR (`payment` / `etax_access` / `feedback` /
   `marketing` / `unknown`) — never assume tax data.
8. Sanity-check every label — a label that fails arithmetic is a
   labelling error, not a review case:
   `ptl validate --doc data/labels/<id>.json` (expect exit 0, except
   known-flag cases like S4's anchorless date).
9. Score a system against the labels:
   `ptl eval --preds preds.json --labels data/labels --faded-ids data/faded.txt`
