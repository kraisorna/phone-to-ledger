"""Muse Spark extractor via Meta Model API (structured output).

Sends one receipt image + extraction prompt; decoding is constrained to
the extraction schema (text.format json_schema), so output always parses
as schema-shaped JSON. Retried once on invalid JSON/structure per 05;
transient transport failures retry 3x with backoff (see base.post_json).
Per-call usage accumulates on .stats (calls/tokens/seconds).
Returns (doc, conf): Spark's field_confidence block with short keys
mapped to dotted field paths (see CONF_KEY_ALIASES), so R12 and the
triage low-confidence check read live values; {} when Spark emits no
block. Non-numeric entries are dropped.

Needs MODEL_API_KEY. Accepts raw bytes, a path, or a Crop carrying
image_path. Crop polygons are NOT rendered yet: the whole source image
is sent, so use one photo per receipt until the crop renderer lands.

temperature defaults to 0 for determinism (None omits it, restoring the
server default). Note temperature alone does not fully determine
outputs: reasoning length and occasional key omissions still vary run
to run (measured live), so downstream validation stays authoritative.

reasoning_effort maps to the Responses API reasoning.effort ladder
(minimal/low/medium/high/xhigh); None omits it (server default).
"none" is rejected by the API for Spark (HTTP 400). Default "low":
measured 58x fewer output tokens (1.9k vs 109k on S6) at comparable
accuracy (3 vs 4 field misses over S1-S6); omissions route to review
via R7/R13, never silently into the ledger. Do not go below "low":
"minimal" measured 0/6 docs correct with 16 field misses at 3.5x the
output tokens of "low" - cheaper in name only.
"""
import base64
import json
import mimetypes
import urllib.error
import urllib.request

from ..pipeline.extract import (EXTRACTION_PROMPT, build_document,
                                normalize_keys)
from ..pipeline.segment import Crop
from ..schema import check_structure, load_schema
from .base import (ATTEMPTS, Extractor, new_stats, post_json,
                   record_call, stamp_source)
from .env import resolve_secret

BASE_URL = "https://api.meta.ai/v1"
MODEL = "muse-spark-1.3"

PROMPT = EXTRACTION_PROMPT  # shared with the Glimmer adapter

# Spark emits short confidence keys (live: grand_total, issuer_tax_id,
# issue_date); R12 and triage read dotted field paths. Unmapped keys
# (line_items, payments, ...) ride through verbatim for future rules.
CONF_KEY_ALIASES = {
    "grand_total": "totals.grand_total",
    "subtotal": "totals.subtotal",
    "vat_amount": "totals.vat_amount",
    "vatable_amount": "totals.vatable_amount",
    "discount_total": "totals.discount_total",
    "total": "totals.total",
    "issue_date": "dates.issue_date",
    "tax_id": "issuer.tax_id",
    "issuer_tax_id": "issuer.tax_id",
    "legal_name": "issuer.legal_name",
    "branch_code": "issuer.branch_code",
    "document_number": "document_number",
}


def normalize_confidence(block):
    """Map a field_confidence block to dotted field paths.

    Non-numeric values (and bools) are dropped: a confidence that is
    not a number carries no signal. Values pass through unclamped.
    """
    out = {}
    for key, value in (block or {}).items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        out[CONF_KEY_ALIASES.get(key, key)] = value
    return out


class SparkExtractor(Extractor):
    # timeout=600: server latency observed up to 257s per call; 300
    # tripped repeatedly (S5/S6 twice, an S1 probe once) while 600s
    # overrides on the same docs succeeded. Matches Glimmer's default.
    def __init__(self, api_key=None, endpoint=BASE_URL, model=MODEL,
                 timeout=600, temperature=0, attempts=ATTEMPTS,
                 reasoning_effort="low"):
        self.api_key = api_key or resolve_secret("MODEL_API_KEY")
        self.endpoint = (endpoint or BASE_URL).rstrip("/")
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self.attempts = attempts
        self.reasoning_effort = reasoning_effort
        self.stats = new_stats()

    def _post(self, payload):
        if not self.api_key:
            raise RuntimeError(
                "Set MODEL_API_KEY (environment or project-root .env; "
                "Meta Model API dashboard > API keys).")
        try:
            return post_json(
                f"{self.endpoint}/responses", payload, self.api_key,
                self.timeout, self.attempts,
                on_response=lambda b, s: record_call(self.stats, b, s))
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

    def extract(self, source, postprocess=True):
        """Return (schema doc, {}) for one receipt image.

        postprocess=False skips build_document (system-B raw baseline):
        no defaults, no embedded-qty strip, no legal fallback, no
        quantity default. Key normalisation always applies: it repairs
        transport artefacts, not extraction content.
        """
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
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.reasoning_effort is not None:
            payload["reasoning"] = {"effort": self.reasoning_effort}
        parsed = None
        for _ in range(2):
            text = self._output_text(self._post(payload))
            try:
                parsed = normalize_keys(json.loads(text))
            except ValueError:
                parsed = None
                continue
            if not check_structure(parsed):
                break
        if not isinstance(parsed, dict):
            raise ValueError("Spark returned no parseable JSON after retry")
        doc = build_document(parsed) if postprocess else parsed
        source_block = doc.setdefault("source", {})
        if isinstance(source_block, dict):
            source_block.setdefault("kind", "ocr")
            source_block["model"] = self.model  # true provenance, not sampled
        conf = normalize_confidence(doc.get("field_confidence"))
        return stamp_source(doc, source), conf
