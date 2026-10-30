"""Schema loader + lightweight validation (stdlib only)."""
import json
import os

SCHEMA_VERSION = "1.0"
_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "extraction_schema.json")

DOCUMENT_TYPES = {"invoice", "tax_invoice", "receipt", "combined", "credit_note",
                  "debit_note", "quotation", "delivery_note", "unknown"}
FORMS = {"full", "abbreviated", "unknown"}
STATUSES = {"paid", "unpaid", "partially_paid", "issued", "draft"}
EMAIL_BLOCKLIST = {"noemail", "no-reply", "noreply", "none@", "test@", "-"}
REQUIRED_TOP = ("schema_version", "document_type", "issuer", "totals")


def load_schema():
    with open(_SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def check_structure(doc):
    """Return list of error strings (empty = structurally valid)."""
    errors = []
    if not isinstance(doc, dict):
        return ["document must be an object"]
    for key in REQUIRED_TOP:
        if key not in doc:
            errors.append(f"missing required field: {key}")
    if doc.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION!r}")
    if doc.get("document_type") not in DOCUMENT_TYPES:
        errors.append(f"bad document_type: {doc.get('document_type')!r}")
    if "form" in doc and doc["form"] not in FORMS:
        errors.append(f"bad form: {doc['form']!r}")
    if "status" in doc and doc["status"] not in STATUSES:
        errors.append(f"bad status: {doc['status']!r}")
    totals = doc.get("totals") or {}
    if "grand_total" not in totals:
        errors.append("missing totals.grand_total")
    for i, li in enumerate(doc.get("line_items") or []):
        if "description" not in li or "line_total" not in li:
            errors.append(f"line_items[{i}] missing description/line_total")
    for i, p in enumerate(doc.get("payments") or []):
        if "amount" not in p:
            errors.append(f"payments[{i}] missing amount")
    return errors


def derive_claim_flag(doc):
    """Only proven-full invoices claim input VAT; derive the flag."""
    doc = dict(doc)
    doc["can_claim_input_vat"] = doc.get("form") == "full"
    return doc
