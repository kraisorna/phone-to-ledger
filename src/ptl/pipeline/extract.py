"""Stage 2: extraction helpers shared by cloud/offline extractors.

The VLM call lives in adapters (spark/glimmer); this module holds
prompt rules and post-processing shared by every extractor:
  - V/N/E suffix stripping, modifier attachment notes
  - POS identifier normalisation (E + 12 alnum)
  - 2-digit BE year stays ambiguous without an anchor
"""
import re

POS_RE = re.compile(r"E[0-9A-Za-z]{12}")
LINE_FLAG_RE = re.compile(r"\s*([VNE])\s*$")
QTY_EMBEDDED_RE = re.compile(r"[xX×]\s*(\d+(?:\.\d+)?)\s*$")

EXTRACTION_PROMPT_RULES = """\
You extract a Thai tax document into schema v1.0 JSON.
- Never take the first date: loyalty expiries and printed-at timestamps are not the doc date.
- 2-digit BE years need a tax-invoice anchor; otherwise era=ambiguous and flag review.
- Totals-only rows are not line items; category subtotals are excluded from line sums.
- 0.00 modifiers attach to their parent line even when priced.
- Keep V/N/E vat flags per line; strip the suffix from the description.
- Output full|abbreviated|unknown form plus can_claim_input_vat.
- Emit per-field confidence 0-1 and raw strings alongside normalised values.
"""


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
    return m.group(0) if m else None


def build_document(skeleton):
    """Fill extraction defaults over a raw extractor dict."""
    doc = dict(skeleton)
    doc.setdefault("schema_version", "1.0")
    doc.setdefault("form", "unknown")
    if "can_claim_input_vat" not in doc:
        doc["can_claim_input_vat"] = doc.get("form") != "abbreviated"
    doc.setdefault("currency", "THB")
    doc.setdefault("vat_rate_bp", 700)
    totals = doc.setdefault("totals", {})
    totals.setdefault("discount_total", 0)
    totals.setdefault("rounding_adjustment", 0)
    totals.setdefault("service_charge", 0)
    totals.setdefault("non_vatable_amount", 0)
    return doc
