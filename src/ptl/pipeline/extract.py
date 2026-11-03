"""Stage 2: extraction helpers shared by cloud/offline extractors.

The VLM call lives in adapters (spark/glimmer); this module holds
prompt rules and post-processing shared by every extractor:
  - V/N/E suffix stripping, modifier attachment notes
  - payment method normalisation (raw tender text -> vocabulary)
  - POS identifier normalisation (E + 12-or-more alnum, never clipped)
  - 2-digit BE year stays ambiguous without an anchor
"""
import re

from ..schema import load_schema

# 02 §9's prose says "E + 12" but its own four examples are E + 14, as
# are all seven observed stamps (S1/S2/S4/S5/S6/S9/S22). Match the full
# run from a token start: clipping a stamp corrupts R10 fuzzy dedup
# keys.
POS_RE = re.compile(r"(?<![0-9A-Za-z])E[0-9A-Za-z]{12,}")
# S9 prints the vendor's own grouping spaced ("E 05 20100 02 A3693"):
# all seven joined stamps segment 2-5-2-5, so accept exactly that shape
# with strict token boundaries on both ends. Anything else spaced is
# not a stamp (None, never a clip or a glued neighbour word).
POS_SPACED_RE = re.compile(r"(?<![0-9A-Za-z])E[ ]+[0-9A-Za-z]{2}"
                           r"[ ]+[0-9A-Za-z]{5}[ ]+[0-9A-Za-z]{2}"
                           r"[ ]+[0-9A-Za-z]{5}(?![0-9A-Za-z])")
LINE_FLAG_RE = re.compile(r"\s*([VNE])\s*$")
QTY_EMBEDDED_RE = re.compile(r"[xX×]\s*(\d+(?:\.\d+)?)\s*$")
LEADING_CODE_RE = re.compile(r"^\d{6}\s+")
TRAILING_BARCODE_RE = re.compile(r"\s+\d{13}$")

EXTRACTION_PROMPT_RULES = """\
You extract a Thai tax document into schema v1.0 JSON.
- Never take the first date: loyalty expiries and printed-at timestamps are not the doc date.
- 2-digit BE years need a tax-invoice anchor; otherwise era=ambiguous and flag review.
- Anchor rule for 2-digit years: only a full YYYYMMDD stamp (TID#20260828...) or an explicit era marker counts; a YYMMDD fragment inside an invoice or reference number (260828-01-07563) never resolves the year - stay ambiguous and flag review.
- branch_code is the store number printed with the merchant address, parenthesized (1681) or leading (14098 Siam Future Esplanade): transcribe it even when unlabeled, never leave it null when printed. A footer outlet label is the same thing: transcribe a Restaurant ID / Store ID / Outlet number as branch_code when no branch-labeled number prints (S9's Restaurant ID 71498).
- when two branch-like numbers appear, branch_code is the one printed with the issuer legal name / merchant address (S1's 00031), not a shop or counter code printed with the brand line (Cafe Amazon's 2083).
- issuer.legal_name is the registered company name alone: strip a trailing branch tail (S1's สาขาที่ 00031) but keep digits belonging to the name (พ.ศ.2515, 2022); never append the brand or store name (S5's CP ALL, not 'CP ALL, 7-Eleven').
- document_number copies a labelled number exactly, keeping attached prefixes (R#0000677955P3, JS001/ESP014867); drop only a detached 'Label:' prefix (No.: 0196768 -> 0196768); with no labelled number use null, never assemble one from store/terminal/sequence stamps. Exception: a bare '#' followed by 15+ digits with no label is the receipt number: strip the '#' and copy the digits (#604002090920260005 -> 604002090920260005); short #-counters (#0007) and letter-codes (C00C5) are never document numbers. An R-prefixed digit run trailing the footer date/time/shop-code line is the receipt number even unlabeled (R000500494).
- Totals-only rows are not line items; category subtotals are excluded from line sums.
- discount_total is only a deduction that lowers the total (subtotal - discount = total); a 'discount' printed among payment/tender rows that leaves the printed total unchanged (QR 35.00 + AIS 10.00 tender against a 45.00 total) is tender, not discount_total: emit 0.
- 0.00 modifiers attach to their parent line even when priced.
- Keep V/N/E vat flags per line; strip the suffix from the description.
- Output full|abbreviated|unknown form plus can_claim_input_vat.
- form is abbreviated only with an explicit ABB mark (TAX INVOICE(ABB), ใบกำกับภาษีอย่างย่อ), full only with buyer name+address+tax ID on the slip, else unknown: never default to abbreviated on a marker-less slip (S23).
- transcribe item descriptions verbatim: drop only obvious printer-stray glyphs (a lone leading letter detached from the name, e.g. 7-Eleven's H prefix) and never expand abbreviations (พาสฯ stays พาสฯ, never พาสเจอร์).
- status is paid only when payment/tender rows are printed and sum to the total, partially_paid when tender covers part, unpaid when no tender rows appear: never invent statuses (no ok/extracted/done).
- Emit per-field confidence 0-1 and raw strings alongside normalised values.
"""

EXTRACTION_PROMPT = (
    "Extract this Thai retail receipt into exactly one JSON object "
    "matching the schema. " + EXTRACTION_PROMPT_RULES + """
Rules: money as INTEGER satang (45.00 THB = 4500); issue_date as
YYYY-MM-DD only, never with a time suffix, plus the verbatim raw string;
a 2-digit year without a corroborating anchor on the slip stays null
with detected_era "ambiguous" (never guess); totals only from
total-labelled rows, tender rows go in payments; transcribe category
subtotal rows as line items flagged is_category_subtotal, never
including them in line sums; modifiers attach to parents via
parent_line_number;
trailing V/N/E is vat_flag; classify form full|abbreviated|unknown.
Ignore printed VATable/VAT figures: always recompute vat_amount =
round(grand_total*7/107) and vatable_amount = grand_total - vat_amount
on inclusive slips.""")


def strip_vat_flag(description):
    """Return (clean_desc, flag) splitting a trailing V/N/E marker."""
    m = LINE_FLAG_RE.search(description or "")
    if not m:
        return description, "unknown"
    return description[:m.start()].rstrip(), m.group(1)


def split_embedded_qty(description):
    """Return (clean_desc, qty|None) for 'NAME X4' style lines."""
    m = QTY_EMBEDDED_RE.search(description or "")
    if not m:
        return description, None
    return description[:m.start()].rstrip(), float(m.group(1))


def normalise_pos_identifier(text):
    m = POS_RE.search(text or "")
    if m:
        return m.group(0)
    m = POS_SPACED_RE.search(text or "")
    return m.group(0).replace(" ", "") if m else None


_R_HASH_RE = re.compile(r"^R#([0-9A-Za-z]{10})P(\d)$")
_R_HASH_BARE_RE = re.compile(r"^(\d{10})P(\d)$")
# 7-Eleven's receipt font confuses these inside the digit run (S22's
# 6 read as G); the run is digits-only in all three gold R#s, so only
# high-confidence pairs map. Anything else passes through untouched.
_R_HASH_FIXES = {"G": "6", "O": "0", "I": "1", "g": "6", "o": "0",
                 "i": "1", "l": "1"}


def normalise_r_hash_receipt_number(value):
    """Repair 7-Eleven R#-receipt-number misreads.

    Gold R#0000677955P3 / R#0000230350P1 / R#0000240606P1 share
    R# + 10 digits + P + digit: letters inside the run (S22 C's G)
    are always misreads and map to their digit, and the bare shape
    regains a dropped R# prefix (S5 D's 0000677955P3). Every other
    shape — letter-bearing formats, short runs, null — passes
    through byte-identical.
    """
    if not isinstance(value, str):
        return value
    m = _R_HASH_RE.match(value)
    if m:
        fixed = "".join(_R_HASH_FIXES.get(ch, ch) for ch in m.group(1))
        return f"R#{fixed}P{m.group(2)}"
    m = _R_HASH_BARE_RE.match(value)
    if m:
        return f"R#{m.group(1)}P{m.group(2)}"
    return value


def normalise_payment_method(method_raw, fallback=None):
    """Map printed tender text to the controlled method vocabulary.

    Live models phrase `method` freely (S1 live emitted "qr"/"other"
    for S1's gold "qr_promptpay"/"voucher_discount"), while the ledger
    and eval need comparable values. Map off the verbatim raw string;
    unknown tender text keeps the model's value: never invent a method.
    """
    text = (method_raw or "").lower()
    if "bank" in text and "qr" in text:
        return "bank_qr"
    if "bank" in text and "transfer" in text:
        return "bank_transfer"
    if ("qr" in text or "qpcb" in text or "promptpay" in text
            or "promptp" in text):
        return "qr_promptpay"
    if ("mastercard" in text or "visa" in text
            or re.search(r"\bmc\b", text)):
        return "credit_card"
    if "truemoney" in text or "ทรู" in text:
        return "truemoney_wallet"
    if "mobile payment" in text:
        return "mobile_payment"
    if "shopee" in text:
        return "shopeefood"
    if "stored" in text and "value" in text:
        return "stored_value_redeem"
    if "redeem" in text and ("sbux" in text or "starbucks" in text):
        return "stored_value_redeem"
    if "ส่วนลด" in text or "discount" in text:
        return "voucher_discount"
    if "cash" in text or "เงินสด" in text:
        return "cash"
    if "card" in text:
        return "card"
    return fallback


_KEY_EDGE_RE = re.compile(r"^[\s\x00-\x1f\x7f-\x9f]+|"
                              r"[\s\x00-\x1f\x7f-\x9f]+$")


def _clean_key(key):
    """Strip edge whitespace and control chars from a dict key."""
    return _KEY_EDGE_RE.sub("", key)


def normalize_keys(node):
    """Strip whitespace and control chars from dict keys, recursively.

    Constrained decoding occasionally emits 'dates '-style duplicate
    keys (seen 1/20 live), and once NUL-suffixed keys ('dates\\0',
    'currency\\0' + 'currency\\x01') that silently dropped fields until
    R1 blocked the row. Exact keys win on collision; stripped dupes
    fill only absent keys. Never mutates the input.
    """
    if isinstance(node, list):
        return [normalize_keys(v) for v in node]
    if not isinstance(node, dict):
        return node
    out = {k: normalize_keys(v) for k, v in node.items()
           if not isinstance(k, str) or k == _clean_key(k)}
    for key, value in node.items():
        if isinstance(key, str) and key != _clean_key(key):
            out.setdefault(_clean_key(key), normalize_keys(value))
    return out


def _strip_embedded_qty(line):
    """Clean one 'NAME X4'-style line; never mutates the input.

    Strips the embedded quantity from the description (keeping the
    verbatim text in description_raw) and fills quantity from the name
    when absent. A quantity that disagrees with the name is left fully
    untouched: a real conflict must stay visible, never be papered over.
    """
    desc = line.get("description") or ""
    clean, qty = split_embedded_qty(desc)
    if qty is None:
        return line
    if line.get("quantity") is not None and line.get("quantity") != qty:
        return line
    out = dict(line)
    out.setdefault("description_raw", desc)
    out["description"] = clean
    if out.get("quantity") is None:
        out["quantity"] = qty
        out["quantity_source"] = "embedded_in_name"
    return out


def _strip_printed_codes(line):
    """Drop glued product codes and barcodes; never mutates the input.

    Watsons prefixes a 6-digit product code (S13/S19) and MR.DIY
    suffixes the EAN-13 barcode (S20); gold keeps the bare name, so
    both go (verbatim text stays in description_raw). A strip that
    would empty the description is skipped: a bare code is data, not
    a name with a code.
    """
    desc = line.get("description") or ""
    clean = TRAILING_BARCODE_RE.sub("", LEADING_CODE_RE.sub("", desc))
    if clean == desc or not clean.strip():
        return line
    out = dict(line)
    out.setdefault("description_raw", desc)
    out["description"] = clean
    return out


def _default_quantity(line):
    """Fill a missing quantity with 1 ('assumed'); copies, never mutates.

    A line with a total but no quantity is a unit sale unless the name
    says otherwise (handled by _strip_embedded_qty first). An explicit
    quantity — even 0 — is always kept: defaults must not mask conflict.
    Subtotal and header rows carry no quantity (gold: null), so the
    default skips them.
    """
    if line.get("quantity") is not None:
        return line
    if line.get("is_category_subtotal") or line.get("is_section_header"):
        return line
    out = dict(line)
    out["quantity"] = 1
    out["quantity_source"] = "assumed"
    return out


def _normalise_payment(pay):
    """Map one payment's method off its raw text; copies, never mutates."""
    out = dict(pay)
    out["method"] = normalise_payment_method(
        pay.get("method_raw"), pay.get("method"))
    return out


def _infer_subtotal(lines, totals):
    """Subtotal from charge lines when the extractor omitted it.

    Mirrors R1's equation and line set (no section headers, no
    category subtotals). Returns None unless every charge line carries
    a numeric total: inference must not manufacture values from
    incomplete data. R1 previously skipped such docs, so filling the
    null weakens no check; transcribed subtotals still face R1 fully.
    """
    charge = [li for li in (lines or [])
              if isinstance(li, dict) and not li.get("is_section_header")
              and not li.get("is_category_subtotal")]
    if not charge:
        return None
    amounts = [li.get("line_total") for li in charge]
    if any(isinstance(a, bool) or not isinstance(a, (int, float))
           for a in amounts):
        return None
    return (sum(amounts) - (totals.get("discount_total") or 0)
            + (totals.get("rounding_adjustment") or 0))


_THAI_DIGIT_TABLE = str.maketrans(
    {chr(0x0E50 + i): str(i) for i in range(10)})


def thai_digits_to_ascii(text):
    """Fold Thai digits (U+0E50-0E59) to ASCII; else pass through."""
    if not isinstance(text, str) or not text:
        return text
    return text.translate(_THAI_DIGIT_TABLE)


def _canonicalise_machine_digits(doc):
    """Fold Thai digits to ASCII in machine-identity fields.

    Thai-digit transcriptions are valid Unicode decimals (R6's
    checksum already accepts them) but split R10 keys across photos
    of one slip and leak non-ASCII digits into the ledger, so the
    machine fields are canonicalised while verbatim prose (names,
    descriptions) is never touched. Copies nested dicts, never
    mutates the input.
    """
    issuer = doc.get("issuer")
    if isinstance(issuer, dict):
        issuer = dict(issuer)
        for key in ("tax_id", "branch_code"):
            if issuer.get(key) is not None:
                issuer[key] = thai_digits_to_ascii(issuer[key])
        doc["issuer"] = issuer
    dates = doc.get("dates")
    if isinstance(dates, dict):
        dates = dict(dates)
        for key in ("issue_date", "raw_date_string"):
            if dates.get(key) is not None:
                dates[key] = thai_digits_to_ascii(dates[key])
        doc["dates"] = dates
    if doc.get("document_number") is not None:
        doc["document_number"] = thai_digits_to_ascii(
            doc["document_number"])
    return doc


def _null_blank_machine_strings(doc):
    """Fold blank machine-identity strings to None.

    Weak extractors emit "" for absent tax IDs, branch codes,
    document numbers and dates (Glimmer D: S24 tax, S2/S25
    docno) while the schema uses null; blanks can never match
    a real gold value, so the fold only ever fixes misses.
    Verbatim prose (legal_name, descriptions) is never touched.
    Copies nested dicts, never mutates the input.
    """
    issuer = doc.get("issuer")
    if isinstance(issuer, dict):
        issuer = dict(issuer)
        for key in ("tax_id", "branch_code"):
            value = issuer.get(key)
            if isinstance(value, str) and not value.strip():
                issuer[key] = None
        doc["issuer"] = issuer
    dates = doc.get("dates")
    if isinstance(dates, dict):
        dates = dict(dates)
        for key, value in dates.items():
            if isinstance(value, str) and not value.strip():
                dates[key] = None
        doc["dates"] = dates
    if (isinstance(doc.get("document_number"), str)
            and not doc["document_number"].strip()):
        doc["document_number"] = None
    return doc


def _infer_total(lines):
    """Gross charge-line sum when the extractor omitted `total`.

    `total` is the pre-deduction ยอดรวม row (net is subtotal), so
    unlike _infer_subtotal this sums charge lines with no discount
    or rounding adjustment. Same completeness bar: None unless
    every charge line carries a numeric total.
    """
    charge = [li for li in (lines or [])
              if isinstance(li, dict) and not li.get("is_section_header")
              and not li.get("is_category_subtotal")]
    if not charge:
        return None
    amounts = [li.get("line_total") for li in charge]
    if any(isinstance(a, bool) or not isinstance(a, (int, float))
           for a in amounts):
        return None
    return sum(amounts)


def _infer_vatable(totals):
    """Vatable from grand-vat-nonvat when the extractor omitted it.

    Mirrors R4's equation, which holds in both inclusive and exclusive
    mode (grand always equals vatable+vat+nonvat). Returns None unless
    grand and vat are both numeric. R4 previously skipped such docs,
    so filling the null weakens no check; transcribed values still
    face R4 fully.
    """
    grand = totals.get("grand_total")
    vat = totals.get("vat_amount")
    if (isinstance(grand, bool) or not isinstance(grand, (int, float))
            or isinstance(vat, bool) or not isinstance(vat, (int, float))):
        return None
    return grand - vat - (totals.get("non_vatable_amount") or 0)


def build_document(skeleton):
    """Fill extraction defaults over a raw extractor dict.

    Also strips embedded quantities ('NAME X4') from line names, so every
    extractor shares one naming convention without prompt duplication,
    defaults a missing line quantity to 1 ('assumed'), and falls back
    issuer.legal_name to brand_name when the extractor only caught the
    trade name (else the ledger seller cell is blank). A missing
    subtotal is computed from charge lines via R1's equation, a
    missing total as the gross charge-line sum, and a missing
    vatable from grand-vat-nonvat via R4's (weak extractors omit
    printed rows); explicit values, even disagreeing ones, are
    never touched. Thai digits in machine-identity fields (tax ID,
    branch, document number, dates) fold to ASCII so re-photos key
    identically, and blank machine-identity strings fold to None
    (the schema's absent marker); verbatim prose is never touched.
    Unknown top-level keys are dropped against the schema's
    properties (decoding glitches emit junk keys; every pipeline
    and adapter write stays inside the schema). Input line/issuer
    dicts are copied, never mutated.
    """
    allowed = set(load_schema().get("properties", {}))
    doc = {k: v for k, v in skeleton.items() if k in allowed}
    doc = _canonicalise_machine_digits(doc)
    doc = _null_blank_machine_strings(doc)
    if doc.get("document_number") is not None:
        doc["document_number"] = normalise_r_hash_receipt_number(
            doc["document_number"])
    issuer = doc.get("issuer")
    if (isinstance(issuer, dict) and not issuer.get("legal_name")
            and issuer.get("brand_name")):
        issuer = dict(issuer)
        issuer["legal_name"] = issuer["brand_name"]
        doc["issuer"] = issuer
    doc.setdefault("schema_version", "1.0")
    doc.setdefault("form", "unknown")
    if doc.get("form") != "full":
        # Only a proven full invoice may claim input VAT: models emit
        # can_claim=True beside abbreviated/unknown forms (Glimmer S6/S1
        # live), which would auto-post a false claim. The guard only
        # ever narrows to False, never grants.
        doc["can_claim_input_vat"] = False
    if "can_claim_input_vat" not in doc:
        doc["can_claim_input_vat"] = doc.get("form") == "full"
    doc.setdefault("currency", "THB")
    doc.setdefault("vat_rate_bp", 700)
    totals = doc.setdefault("totals", {})
    totals.setdefault("discount_total", 0)
    totals.setdefault("rounding_adjustment", 0)
    totals.setdefault("service_charge", 0)
    totals.setdefault("non_vatable_amount", 0)
    lines = doc.get("line_items")
    if lines:
        doc["line_items"] = [
            _default_quantity(_strip_embedded_qty(_strip_printed_codes(li)))
            if isinstance(li, dict) else li for li in lines]
    payments = doc.get("payments")
    if payments:
        doc["payments"] = [
            _normalise_payment(p) if isinstance(p, dict) else p
            for p in payments]
    if totals.get("subtotal") is None:
        inferred = _infer_subtotal(doc.get("line_items"), totals)
        if inferred is not None:
            totals["subtotal"] = inferred
    if totals.get("total") is None:
        inferred = _infer_total(doc.get("line_items"))
        if inferred is not None:
            totals["total"] = inferred
    if totals.get("vatable_amount") is None:
        inferred = _infer_vatable(totals)
        if inferred is not None:
            totals["vatable_amount"] = inferred
    return doc
