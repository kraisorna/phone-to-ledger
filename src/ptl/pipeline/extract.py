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
- document_number copies a labelled number exactly, keeping attached prefixes (R#0000677955P3, JS001/ESP014867); drop only a detached 'Label:' prefix (No.: 0196768 -> 0196768); with no labelled number use null, never assemble one from store/terminal/sequence stamps.
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


def build_document(skeleton):
    """Fill extraction defaults over a raw extractor dict.

    Also strips embedded quantities ('NAME X4') from line names, so every
    extractor shares one naming convention without prompt duplication,
    defaults a missing line quantity to 1 ('assumed'), and falls back
    issuer.legal_name to brand_name when the extractor only caught the
    trade name (else the ledger seller cell is blank).
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
    if "can_claim_input_vat" not in doc:
        doc["can_claim_input_vat"] = doc.get("form") != "abbreviated"
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
    return doc
