"""Stage 4: export a validated document to a ledger row (CSV/XLSX).

Columns are the 05 section 5 minimum, in order, plus a trailing `note`
extension: date, document_number, document_type, form,
can_claim_input_vat, seller legal/tax/branch, vatable, vat,
non_vatable, grand_total, payment_method, review_status,
source_image_ref.
Money stored satang, exported THB 2dec. Duplicates excluded with a note,
never merged. ABB kept, marked unclaimable.
"""
import csv
import io

from ..money import to_thb

COLUMNS = ["date", "document_number", "document_type", "form",
           "can_claim_input_vat", "seller_legal_name", "seller_tax_id",
           "branch_code", "vatable", "vat", "non_vatable", "grand_total",
           "payment_method", "review_status", "source_image_ref", "note"]


def to_row(doc, review_status="auto_accept", note=""):
    t = doc.get("totals") or {}
    issuer = doc.get("issuer") or {}
    pays = doc.get("payments") or []
    return {
        "date": (doc.get("dates") or {}).get("issue_date") or "",
        "document_number": doc.get("document_number") or "",
        "document_type": doc.get("document_type") or "",
        "form": doc.get("form") or "",
        "can_claim_input_vat": ("yes" if doc.get("can_claim_input_vat", True)
                                else "no"),
        "seller_legal_name": issuer.get("legal_name") or "",
        "seller_tax_id": issuer.get("tax_id") or "",
        "branch_code": issuer.get("branch_code") or "",
        "vatable": to_thb(t.get("vatable_amount")),
        "vat": to_thb(t.get("vat_amount")),
        "non_vatable": to_thb(t.get("non_vatable_amount")),
        "grand_total": to_thb(t.get("grand_total")),
        "payment_method": "+".join(p.get("method", "") for p in pays),
        "review_status": review_status,
        "source_image_ref": (doc.get("source") or {}).get("image_uri") or "",
        "note": note,
    }


def to_csv(rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS)
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in COLUMNS})
    return buf.getvalue()


def to_xlsx(rows, path):
    """Write XLSX; needs openpyxl (optional dependency)."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "ledger"
    ws.append(COLUMNS)
    for r in rows:
        ws.append([r.get(c, "") for c in COLUMNS])
    wb.save(path)
    return path
