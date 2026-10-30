"""Glimmer offline adapter: local Ollama extraction, no cloud upload.

Same adapter interfaces and pipeline code as the cloud path; the
model is meta's open-weights muse-glimmer served by a local Ollama
daemon (default http://localhost:11434). Needs `ollama pull
muse-glimmer` once (~18GB); afterwards fully offline. Extraction runs
four short prompts (header, lines, dates, form) instead of the shared
EXTRACTION_PROMPT: one shot drops whole sections on the 30B model.

Segmentation is one whole-image crop per photo: a text-first VLM cannot
emit SAM-grade polygons, and current usage is one receipt per photo.
True offline segmentation (local SAM weights) is still future work.
"""
import base64
import json
import mimetypes
import struct
import urllib.error
import urllib.request

from .base import Extractor, Reviewer, Segmenter, stamp_source
from ..pipeline.extract import (EXTRACTION_PROMPT, build_document,
                                normalize_keys)
from ..pipeline.segment import Crop
from ..pipeline.triage import triage
from ..schema import load_schema

OLLAMA_URL = "http://localhost:11434"
MODEL = "muse-glimmer"

SETUP_HINT = ("Is Ollama running with the model pulled? "
              "`ollama serve` in one shell, `ollama pull muse-glimmer` "
              "once (~18GB), then retry.")

# Four-pass prompts: the 30B local model drops whole sections
# (dates, lines, tax ID, form) under the full shared prompt but handles
# each section cleanly when asked alone (S6 lines-only, dates-only and
# form-only probes returned exact seed values). Passes own disjoint
# sections, so merging cannot conflict: each dedicated pass owns its
# section unconditionally.
HEADER_PROMPT = (
    "Transcribe this Thai retail receipt into the schema JSON: issuer "
    "legal name, brand, branch_code and 13-digit tax_id; "
    "document_number; totals in INTEGER satang (45.00 THB = 4500). "
    "Leave dates and line_items EMPTY: other passes handle them. "
    "branch_code is the number printed with the issuer legal name / "
    "merchant address (S00031 style branch), not a shop code printed "
    "with the brand line; legal_name is the registered company name "
    "alone, without any branch suffix.")
LINES_PROMPT = (
    "Transcribe ONLY the purchased line items from this Thai retail "
    "receipt into the schema JSON. For each bought product write one "
    "entry in line_items with description, quantity and line_total in "
    "INTEGER satang (32.00 THB = 3200). Ignore totals, dates, tax ID "
    "and all other fields: leave them null or empty. Totals-only rows "
    "and subtotals are not line items.")
DATES_PROMPT = (
    "Read ONLY the document date from this Thai retail receipt into "
    "the schema JSON: fill dates.issue_date as YYYY-MM-DD plus the "
    "verbatim raw string in dates.raw_date_string. Ignore everything "
    "else: leave all other fields null or empty.")
FORM_PROMPT = (
    "Classify ONLY the invoice form of this Thai retail receipt into "
    "the schema JSON: set form to abbreviated when the header shows an "
    "ABB mark such as TAX INVOICE(ABB), to full for a full tax invoice "
    "with buyer details, else unknown. Abbreviated slips cannot claim "
    "input VAT. Ignore everything else: leave all other fields null "
    "or empty.")


def _merge_passes(header_doc, lines_doc, dates_doc, form_doc):
    """Combine the four passes; dedicated passes own their sections."""
    merged = dict(header_doc)
    merged["line_items"] = lines_doc.get("line_items") or []
    merged["dates"] = dates_doc.get("dates") or {}
    merged["form"] = form_doc.get("form") or "unknown"
    merged["can_claim_input_vat"] = bool(form_doc.get("can_claim_input_vat"))
    return merged


def _image_size(path):
    """Return (width, height) for a PNG/JPEG file, stdlib-only."""
    with open(path, "rb") as f:
        head = f.read(26)
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        width, height = struct.unpack(">II", head[16:24])
        return width, height
    if head[:2] == b"\xff\xd8":
        return _jpeg_size(path)
    raise ValueError(f"unsupported image type for {path}")


def _jpeg_size(path):
    sof_markers = (set(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC})
    with open(path, "rb") as f:
        data = f.read()
    pos = 2
    while pos + 9 < len(data):
        if data[pos] != 0xFF:
            break
        marker = data[pos + 1]
        if marker in sof_markers:
            height, width = struct.unpack(">HH", data[pos + 5:pos + 9])
            return width, height
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            pos += 2
            continue
        (length,) = struct.unpack(">H", data[pos + 2:pos + 4])
        pos += 2 + length
    raise ValueError(f"no SOF marker in {path}")


class GlimmerSegmenter(Segmenter):
    def segment(self, image_path):
        """Return one whole-image Crop; raises on missing/unreadable files."""
        width, height = _image_size(str(image_path))
        return [Crop(index=0,
                     polygon=[[0, 0], [width, 0],
                              [width, height], [0, height]],
                     image_path=str(image_path))]


class GlimmerExtractor(Extractor):
    def __init__(self, endpoint=OLLAMA_URL, model=MODEL, timeout=600,
                 temperature=0, num_ctx=8192, think=False):
        self.endpoint = (endpoint or OLLAMA_URL).rstrip("/")
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self.num_ctx = num_ctx
        self.think = think

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

    def _post(self, messages):
        # think=False: hidden thinking costs ~150 tokens even on trivial
        # calls (measured 73s vs 2s), and a think-enabled full receipt
        # exceeded 40 min without any output; no-think completes in ~8
        # min. Revisit only with evidence it converges.
        payload = {"model": self.model, "stream": False,
                   "think": self.think,
                   "messages": messages, "format": load_schema()}
        # Ollama's default 32k context starves a 30B model on 32GB
        # unified memory (measured 1.4 tok/s); 8k fits our prompt easily.
        options = {}
        if self.temperature is not None:
            options["temperature"] = self.temperature
        if self.num_ctx is not None:
            options["num_ctx"] = self.num_ctx
        if options:
            payload["options"] = options
        req = urllib.request.Request(
            f"{self.endpoint}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req,
                                        timeout=self.timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise RuntimeError(
                    "Ollama has no model "
                    f"{self.model!r} on this machine. {SETUP_HINT}"
                ) from e
            raise
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"cannot reach Ollama at {self.endpoint} ({e}). {SETUP_HINT}"
            ) from e

    def _extract_with(self, image_b64, prompt):
        """Run one prompt over the image; return the built doc."""
        messages = [{"role": "user", "content": prompt,
                     "images": [image_b64]}]
        body = self._post(messages)
        text = ((body.get("message") or {}).get("content") or "")
        if "<|" in text:  # no-think mode leaks an <|eot|> trailer
            text = text[:text.index("<|")]
        doc = build_document(normalize_keys(json.loads(text)))
        source_block = doc.setdefault("source", {})
        if isinstance(source_block, dict):
            source_block.setdefault("kind", "ocr")
            source_block["model"] = self.model
        return doc

    def extract(self, source, single_pass=False):
        """Return (schema doc, {}) for one receipt image, fully offline.

        Four passes by default (header, lines, dates, form, merged):
        the local model misses whole sections in one shot.
        single_pass=True keeps the legacy single EXTRACTION_PROMPT call.
        """
        # Ollama takes raw base64 and sniffs the container; mime unused.
        _, raw = self._image_payload(source)
        image_b64 = base64.b64encode(raw).decode("ascii")
        if single_pass:
            doc = self._extract_with(image_b64, EXTRACTION_PROMPT)
            return stamp_source(doc, source), {}
        header = self._extract_with(image_b64, HEADER_PROMPT)
        lines = self._extract_with(image_b64, LINES_PROMPT)
        dates = self._extract_with(image_b64, DATES_PROMPT)
        form = self._extract_with(image_b64, FORM_PROMPT)
        # Finalize the merged doc: cross-section defaults (e.g. subtotal
        # inference from merged lines) only fire on the whole document.
        # build_document never overwrites explicit values, so this is
        # idempotent over the per-pass builds above.
        doc = build_document(_merge_passes(header, lines, dates, form))
        return stamp_source(doc, source), {}


class GlimmerReviewer(Reviewer):
    def review(self, doc, validation):
        return triage(doc, validation)
