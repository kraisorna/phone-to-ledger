"""SAM 3.1 segmenter via Meta Model API (Responses API, non-streaming).

Sends one image + one concept noun phrase (default "receipt"); every
returned box becomes a Crop with its polygon in original-image pixels
(verified live: the box frame w/h equals the source JPEG dimensions).

Needs MODEL_API_KEY in the environment (or api_key=...). Masks in the
grammar are ignored: crops come from boxes. Raises loudly on auth /
entitlement errors and on non-empty output without boxes; empty output
means no receipts found (verified with a negative concept).

Crops come back deskewed=False, partial=False: no reliable partial
signal exists in boxes alone (a complete slip can touch frame edges),
and perspective-correct rendering is a later stage.
"""
import base64
import json
import mimetypes
import os
import re
import urllib.error
import urllib.request

from ..pipeline.segment import Crop
from .base import Segmenter

BASE_URL = "https://api.meta.ai/v1"
MODEL = "sam-3.1"
CONCEPT = "receipt"

BOX_RE = re.compile(r"<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);"
                    r"w=(\d+);h=(\d+)\|>")


class Sam31Segmenter(Segmenter):
    def __init__(self, api_key=None, endpoint=BASE_URL, model=MODEL,
                 concept=CONCEPT, timeout=300):
        self.api_key = api_key or os.environ.get("MODEL_API_KEY")
        self.endpoint = (endpoint or BASE_URL).rstrip("/")
        self.model = model
        self.concept = concept
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
                    "SAM request rejected (401): bad or missing API key."
                ) from e
            if e.code == 404:
                raise RuntimeError(
                    "SAM model not found (404): this key lacks the "
                    f"{self.model} entitlement; check dashboard access."
                ) from e
            raise

    @staticmethod
    def _data_url(image_path):
        mime, _ = mimetypes.guess_type(image_path)
        if mime is None:
            raise ValueError(f"cannot infer media type for {image_path}")
        with open(image_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{encoded}"

    @classmethod
    def boxes_from_text(cls, text):
        """Return [(x1, y1, x2, y2, w, h)] from SAM output text.

        Blank text means no matches. Non-blank text without a valid box
        record means the grammar changed: fail loudly, never silently.
        """
        boxes = []
        for m in BOX_RE.finditer(text or ""):
            x1, y1, x2, y2, w, h = (int(g) for g in m.groups())
            if not (w > 0 and h > 0 and 0 <= x1 < x2 <= w
                    and 0 <= y1 < y2 <= h):
                raise ValueError(f"invalid SAM box record: {m.group(0)}")
            boxes.append((x1, y1, x2, y2, w, h))
        if not boxes and (text or "").strip():
            raise ValueError("SAM output has no box records; "
                             f"grammar may have changed: {text[:120]!r}")
        return boxes

    def segment(self, image_path):
        """Return one Crop per receipt box, polygons in source pixels."""
        payload = {
            "model": self.model,
            "stream": False,
            "input": [{"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": self.concept},
                {"type": "input_image",
                 "image_url": self._data_url(image_path)},
            ]}],
        }
        doc = self._post(payload)
        texts = [part.get("text", "")
                 for item in (doc.get("output") or [])
                 for part in (item.get("content") or [])
                 if part.get("type") == "output_text"]
        boxes = []
        for text in texts:
            boxes.extend(self.boxes_from_text(text))
        return [Crop(index=i,
                     polygon=[[x1, y1], [x2, y1], [x2, y2], [x1, y2]])
                for i, (x1, y1, x2, y2, _w, _h) in enumerate(boxes)]
