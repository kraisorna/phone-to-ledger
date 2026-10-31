"""Stage 2: extraction helpers shared by cloud/offline extractors.

The VLM call lives in adapters (spark/glimmer); this module holds
prompt rules and post-processing shared by every extractor:
  - V/N/E suffix stripping, modifier attachment notes
  - payment method normalisation (raw tender text -> vocabulary)
  - POS identifier normalisation (E + 12-or-more alnum, never clipped)
  - 2-digit BE year stays ambiguous without an anchor
"""
import re

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

EXTRACTION_PROMPT_RULES = """\
You extract a Thai tax document into schema v1.0 JSON.
- Never take the first date: loyalty expiries and printed-at timestamps are not the doc date.
- 2-digit BE years need a tax-invoice anchor; otherwise era=ambiguous and flag review.
- Anchor rule for 2-digit years: only a full YYYYMMDD stamp (TID#20260828...) or an explicit era marker counts; a YYMMDD fragment inside an invoice or reference number (260828-01-07563) never resolves the year - stay ambiguous and flag review.
- branch_code is the store number printed with the merchant address, parenthesized (1681) or leading (14098 Siam Future Esplanade): transcribe it even when unlabeled, never leave it null when printed.
- when two branch-like numbers appear, branch_code is the one printed with the issuer legal name / merchant address (S1's 00031), not a shop or counter code printed with the brand line (Cafe Amazon's 2083).
- document_number copies a labelled number exactly, keeping attached prefixes (R#0000677955P3, JS001/ESP014867); drop only a detached 'Label:' prefix (No.: 0196768 -> 0196768); with no labelled number use null, never assemble one from store/terminal/sequence stamps.
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
total-labelled rows, tender rows go in payments; category subtotals are
not line items; modifiers attach to parents via parent_line_number;
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
    if "qr" in text or "promptpay" in text or "promptp" in text:
        return "qr_promptpay"
    if ("mastercard" in text or "visa" in text
            or re.search(r"\bmc\b", text)):
        return "credit_card"
    if "truemoney" in text or "ทรู" in text:
        return "truemoney_wallet"
    if "mobile payment" in text:
        return "mobile_payment"
    if "stored" in text and "value" in text:
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


def _default_quantity(line):
    """Fill a missing quantity with 1 ('assumed'); copies, never mutates.

    A line with a total but no quantity is a unit sale unless the name
    says otherwise (handled by _strip_embedded_qty first). An explicit
    quantity — even 0 — is always kept: defaults must not mask conflict.
    """
    if line.get("quantity") is not None:
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
    subtotal is computed from charge lines via R1's equation and a
    missing vatable from grand-vat-nonvat via R4's (weak extractors
    omit printed rows); explicit values, even disagreeing ones, are
    never touched.
    Input line/issuer dicts are copied, never mutated.
    """
    doc = dict(skeleton)
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
            _default_quantity(_strip_embedded_qty(li))
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
    if totals.get("vatable_amount") is None:
        inferred = _infer_vatable(totals)
        if inferred is not None:
            totals["vatable_amount"] = inferred
    return doc
