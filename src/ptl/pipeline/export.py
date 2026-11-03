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
import os
import re
import zipfile
from xml.sax.saxutils import escape

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


def append_csv(path, rows):
    """Append rows to a ledger CSV, creating it with a header if missing.

    Refuses with ValueError when the existing file's header is not
    exactly COLUMNS, so a ledger is never polluted by a foreign file.
    Returns path.
    """
    body = io.StringIO()
    w = csv.DictWriter(body, fieldnames=COLUMNS)
    for r in rows:
        w.writerow({c: r.get(c, "") for c in COLUMNS})
    existing = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            existing = f.read()
    if not existing:
        prefix = ",".join(COLUMNS) + "\r\n"
    else:
        if existing.splitlines()[0] != ",".join(COLUMNS):
            raise ValueError(f"{path}: header mismatch; refusing to append")
        prefix = "" if existing.endswith("\n") else "\n"
    with open(path, "a", encoding="utf-8", newline="") as f:
        f.write(prefix + body.getvalue())
    return path


_XML_BAD = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _col_letter(n):
    out = ""
    while True:
        n, rem = divmod(n, 26)
        out = chr(65 + rem) + out
        if not n:
            return out
        n -= 1


def _sheet_xml(rows):
    lines = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
             '<worksheet xmlns="http://schemas.openxmlformats.org/'
             'spreadsheetml/2006/main"><sheetData>']
    for i, values in enumerate([COLUMNS] + [[r.get(c, "") for c in COLUMNS]
                                            for r in rows], start=1):
        cells = []
        for j, v in enumerate(values):
            text = escape(_XML_BAD.sub("", str(v)))
            cells.append(f'<c r="{_col_letter(j)}{i}" t="inlineStr">'
                         f"<is><t>{text}</t></is></c>")
        lines.append(f"<row r=\"{i}\">" + "".join(cells) + "</row>")
    lines.append("</sheetData></worksheet>")
    return "".join(lines)


def to_xlsx(rows, path):
    """Write a minimal stdlib-only XLSX ledger (inline strings)."""
    content_types = ('<?xml version="1.0" encoding="UTF-8"?>'
                     '<Types xmlns="http://schemas.openxmlformats.org/'
                     'package/2006/content-types">'
                     '<Default Extension="rels" ContentType="application/'
                     'vnd.openxmlformats-package.relationships+xml"/>'
                     '<Default Extension="xml" ContentType="application/xml"/>'
                     '<Override PartName="/xl/workbook.xml" ContentType='
                     '"application/vnd.openxmlformats-officedocument.'
                     'spreadsheetml.sheet.main+xml"/>'
                     '<Override PartName="/xl/worksheets/sheet1.xml" '
                     'ContentType="application/vnd.openxmlformats-'
                     'officedocument.spreadsheetml.worksheet+xml"/>'
                     "</Types>")
    rels = ('<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/'
            'package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.'
            'openxmlformats.org/officeDocument/2006/relationships/'
            'officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>")
    workbook = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/'
                'spreadsheetml/2006/main" xmlns:r="http://schemas.'
                'openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="ledger" sheetId="1" r:id="rId1"/>'
                "</sheets></workbook>")
    wb_rels = ('<?xml version="1.0" encoding="UTF-8"?>'
               '<Relationships xmlns="http://schemas.openxmlformats.org/'
               'package/2006/relationships">'
               '<Relationship Id="rId1" Type="http://schemas.'
               'openxmlformats.org/officeDocument/2006/relationships/'
               'worksheet" Target="worksheets/sheet1.xml"/>'
               "</Relationships>")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        z.writestr("xl/worksheets/sheet1.xml", _sheet_xml(rows))
    return path
