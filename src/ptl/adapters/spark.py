"""Muse Spark extractor via Meta Model API (structured output).

Sends one receipt image + extraction prompt; decoding is constrained to
the extraction schema (text.format json_schema), so output always parses
as schema-shaped JSON. Retried once on invalid JSON/structure per 05.
Returns (doc, {}) — per-field confidence is unknown and R12 skips it.

Needs MODEL_API_KEY. Accepts raw bytes, a path, or a Crop carrying
image_path. Crop polygons are NOT rendered yet: the whole source image
is sent, so use one photo per receipt until the crop renderer lands.
"""
import base64
import json
import mimetypes
import os
import urllib.error
import urllib.request

from ..pipeline.extract import EXTRACTION_PROMPT_RULES, build_document
from ..pipeline.segment import Crop
from ..schema import check_structure, load_schema
from .base import Extractor

BASE_URL = "https://api.meta.ai/v1"
MODEL = "muse-spark-1.3"

PROMPT = ("Extract this Thai retail receipt into exactly one JSON object "
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


class SparkExtractor(Extractor):
    def __init__(self, api_key=None, endpoint=BASE_URL, model=MODEL,
                 timeout=300):
        self.api_key = api_key or os.environ.get("MODEL_API_KEY")
        self.endpoint = (endpoint or BASE_URL).rstrip("/")
        self.model = model
        self.timeout = timeout

    def _post(self, payload):
        if not self.api_key:
            raise RuntimeError(
                "Set MODEL_API_KEY (Meta Model API dashboard > API keys).")
        req = urllib.request.Request(
            f"{self.endpoint}/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise RuntimeError(
                    "Spark request rejected (401): bad or missing API key."
                ) from e
            if e.code == 404:
                raise RuntimeError(
                    "Spark model not found (404): this key lacks the "
                    f"{self.model} entitlement; check dashboard access."
                ) from e
            raise

    @staticmethod
    def _image_payload(source):
        """Return (mime, raw bytes) for bytes | path | Crop."""
        if isinstance(source, (bytes, bytearray)):
            raw = bytes(source)
            if raw[:2] == b"\xff\xd8":
                return "image/jpeg", raw
            if raw[:4] == b"\x89PNG":
                return "image/png", raw
            raise ValueError("cannot infer image type from raw bytes")
        if isinstance(source, Crop):
            if not source.image_path:
                raise ValueError("Crop carries no image_path; pass the "
                                 "source bytes or path instead")
            source = source.image_path
        mime, _ = mimetypes.guess_type(str(source))
        if mime is None:
            raise ValueError(f"cannot infer media type for {source}")
        with open(source, "rb") as f:
            return mime, f.read()

    @staticmethod
    def _output_text(doc):
        for item in (doc.get("output") or []):
            for part in (item.get("content") or []):
                if part.get("type") == "output_text" and part.get("text"):
                    return part["text"]
        return ""

    def extract(self, source):
        """Return (schema doc, {}) for one receipt image."""
        mime, raw = self._image_payload(source)
        data_url = (f"data:{mime};base64,"
                    + base64.b64encode(raw).decode("ascii"))
        payload = {
            "model": self.model,
            "stream": False,
            "input": [{"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": PROMPT},
                {"type": "input_image", "image_url": data_url},
            ]}],
            "text": {"format": {"type": "json_schema",
                                "name": "ReceiptExtraction",
                                "schema": load_schema()}},
        }
        parsed = None
        for _ in range(2):
            text = self._output_text(self._post(payload))
            try:
                parsed = json.loads(text)
            except ValueError:
                parsed = None
                continue
            if not check_structure(parsed):
                break
        if not isinstance(parsed, dict):
            raise ValueError("Spark returned no parseable JSON after retry")
        doc = build_document(parsed)
        source_block = doc.setdefault("source", {})
        if isinstance(source_block, dict):
            source_block.setdefault("kind", "ocr")
            source_block["model"] = self.model  # true provenance, not sampled
        return doc, {}
