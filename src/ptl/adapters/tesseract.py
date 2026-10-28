"""Tesseract + regex baseline adapter (system A).

Needs `tesseract` binary with tha+eng data; regexes target ABB slips.
"""
import re
import subprocess

from .base import Extractor
from ..pipeline.extract import (build_document, normalise_pos_identifier,
                                strip_vat_flag)
from ..money import to_satang

TOTAL_RES = [re.compile(r"(?:TOTAL|ยอดรวม|รวมทั้งสิ้น)\s*[: ]\s*([\d,]+\.\d{2})"),
             re.compile(r"([\d,]+\.\d{2})\s*$")]
DATE_RE = re.compile(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})")
TAX_RE = re.compile(r"(\d{13})")


class TesseractExtractor(Extractor):
    def __init__(self, lang="tha+eng"):
        self.lang = lang

    def ocr(self, image_path):
        out = subprocess.run(["tesseract", image_path, "stdout", "-l", self.lang],
                             capture_output=True, text=True, check=True)
        return out.stdout

    def parse(self, text):
        totals, dates, tax_ids = [], [], []
        for line in text.splitlines():
            for rx in TOTAL_RES:
                m = rx.search(line)
                if m:
                    totals.append(to_satang(m.group(1).replace(",", "")))
            m = DATE_RE.search(line)
            if m:
                dates.append(m.group(1))
            m = TAX_RE.search(line)
            if m:
                tax_ids.append(m.group(1))
        grand = totals[-1] if totals else 0
        return build_document({
            "document_type": "unknown",
            "issuer": {"tax_id": tax_ids[-1] if tax_ids else None},
            "dates": {"raw_date_string": dates[0] if dates else None},
            "totals": {"grand_total": grand},
            "pos_identifier": normalise_pos_identifier(text),
            "source": {"kind": "ocr", "model": "tesseract+regex"},
            "field_confidence": {},
        })

    def extract(self, crop):
        raise NotImplementedError("pass an image path to .ocr() then .parse()")
