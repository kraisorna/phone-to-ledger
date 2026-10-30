"""Glimmer offline adapter: local Ollama extraction (HTTP mocked).

Live behaviour (muse-glimmer local model, whole-image crop, schema
format) is verified against a local Ollama server; these tests pin
request shapes, parsing, and error paths without loading the model.
"""
import base64
import io
import json
import os
import struct
import tempfile
import unittest
import urllib.error
from unittest import mock

from ptl.adapters.glimmer import (DATES_PROMPT, FORM_PROMPT,
                                  HEADER_PROMPT, LINES_PROMPT,
                                  GlimmerExtractor, GlimmerReviewer,
                                  GlimmerSegmenter)
from ptl.pipeline.extract import EXTRACTION_PROMPT
from ptl.pipeline.segment import Crop
from ptl.pipeline.triage import triage
from ptl.pipeline.validate_rules import validate
from ptl.schema import load_schema
from tests.fixtures import fresh


def _png_bytes(w, h):
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr
            + b"\x00\x00\x00\x00")


def _jpg_bytes(w, h):
    app0 = b"\xff\xe0\x00\x10" + b"J" * 14
    sof0 = (b"\xff\xc0\x00\x08\x08" + struct.pack(">H", h)
            + struct.pack(">H", w) + b"\x01")
    return b"\xff\xd8" + app0 + sof0 + b"\xff\xd9"


def _write(path, data):
    with open(path, "wb") as f:
        f.write(data)
    return path


def _chat_ok(content):
    body = {"message": {"role": "assistant", "content": content},
            "done": True}
    resp = mock.MagicMock()
    resp.__enter__.return_value = io.StringIO(json.dumps(body))
    resp.__exit__.return_value = False
    return mock.MagicMock(return_value=resp)


def _chat_repeat(content):
    """urlopen mock serving a fresh copy of one response on every call.

    Count-agnostic: pass-count changes must only touch the tests that
    pin the pass count, never the parsing/options tests.
    """
    return mock.MagicMock(
        side_effect=lambda *a, **k: _chat_ok(content)())


def _http_error(code, body=b""):
    return urllib.error.HTTPError("http://localhost:11434/api/chat", code,
                                  "x", {}, io.BytesIO(body))


class TestGlimmerSegment(unittest.TestCase):
    def test_png_full_frame_crop(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.png"), _png_bytes(200, 100))
            (crop,) = GlimmerSegmenter().segment(img)
        self.assertEqual(crop.index, 0)
        self.assertEqual(crop.polygon,
                         [[0, 0], [200, 0], [200, 100], [0, 100]])
        self.assertEqual(crop.image_path, img)
        self.assertFalse(crop.partial)

    def test_jpg_skips_app0(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"), _jpg_bytes(1199, 3665))
            (crop,) = GlimmerSegmenter().segment(img)
        self.assertEqual(crop.polygon[2], [1199, 3665])

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            GlimmerSegmenter().segment("/no/such/r.jpg")

    def test_garbage_bytes_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"), b"not-an-image")
            with self.assertRaises(ValueError):
                GlimmerSegmenter().segment(img)


class TestGlimmerExtract(unittest.TestCase):
    def test_roundtrip(self):
        ext = GlimmerExtractor()
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"), _jpg_bytes(8, 8))
            with mock.patch("ptl.adapters.glimmer.urllib.request.urlopen",
                            _chat_repeat(json.dumps(fresh()))):
                doc, conf = ext.extract(img)
        self.assertEqual(doc["totals"]["grand_total"], 10700)
        self.assertEqual(conf, {})
        self.assertEqual(doc["source"]["model"], "muse-glimmer")
        self.assertEqual(doc["source"]["kind"], "ocr")

    def test_request_shape(self):
        ext = GlimmerExtractor()
        raw = _jpg_bytes(8, 8)
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"), raw)
            opener = _chat_ok(json.dumps(fresh()))
            with mock.patch("ptl.adapters.glimmer.urllib.request.urlopen",
                            opener):
                ext.extract(img, single_pass=True)
        (req,), _ = opener.call_args
        self.assertTrue(req.full_url.endswith("/api/chat"))
        payload = json.loads(req.data)
        self.assertEqual(payload["model"], "muse-glimmer")
        self.assertFalse(payload["stream"])
        self.assertFalse(payload["think"])
        self.assertEqual(payload["messages"][0]["content"],
                         EXTRACTION_PROMPT)
        self.assertEqual(payload["messages"][0]["images"],
                         [base64.b64encode(raw).decode("ascii")])
        self.assertEqual(payload["options"], {"temperature": 0,
                                              "num_ctx": 8192})
        self.assertEqual(payload["format"], load_schema())

    def test_spaced_keys_normalized(self):
        ext = GlimmerExtractor()
        messy = {"dates ": {"issue_date": "2026-08-28"},
                 "totals": {"grand_total": 100}}
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"), _jpg_bytes(8, 8))
            with mock.patch("ptl.adapters.glimmer.urllib.request.urlopen",
                            _chat_repeat(json.dumps(messy))):
                doc, _ = ext.extract(img)
        self.assertEqual(doc["dates"]["issue_date"], "2026-08-28")

    def test_eot_trailer_stripped(self):
        ext = GlimmerExtractor()
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"), _jpg_bytes(8, 8))
            with mock.patch("ptl.adapters.glimmer.urllib.request.urlopen",
                            _chat_repeat(json.dumps(fresh()) + "<|eot|>")):
                doc, _ = ext.extract(img)
        self.assertEqual(doc["totals"]["grand_total"], 10700)

    def test_crop_and_bytes_inputs(self):
        ext = GlimmerExtractor()
        raw = _jpg_bytes(8, 8)
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"), raw)
            opener = _chat_repeat(json.dumps(fresh()))
            with mock.patch("ptl.adapters.glimmer.urllib.request.urlopen",
                            opener):
                ext.extract(Crop(index=0, polygon=[], image_path=img))
                ext.extract(bytes(raw))
        for call in opener.call_args_list:
            (req,), _ = call
            sent = json.loads(req.data)["messages"][0]["images"][0]
            self.assertEqual(sent, base64.b64encode(raw).decode("ascii"))

    def test_temperature_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"), _jpg_bytes(8, 8))
            opener = _chat_repeat(json.dumps(fresh()))
            with mock.patch("ptl.adapters.glimmer.urllib.request.urlopen",
                            opener):
                GlimmerExtractor(temperature=None).extract(img)
        (req,), _ = opener.call_args
        self.assertEqual(json.loads(req.data)["options"], {"num_ctx": 8192})

    def test_options_omitted_when_all_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"), _jpg_bytes(8, 8))
            opener = _chat_repeat(json.dumps(fresh()))
            with mock.patch("ptl.adapters.glimmer.urllib.request.urlopen",
                            opener):
                GlimmerExtractor(temperature=None, num_ctx=None).extract(img)
        (req,), _ = opener.call_args
        self.assertNotIn("options", json.loads(req.data))

    def test_connection_refused_points_at_setup(self):
        ext = GlimmerExtractor()
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"), _jpg_bytes(8, 8))
            with mock.patch("ptl.adapters.glimmer.urllib.request.urlopen",
                            side_effect=urllib.error.URLError(
                                "connection refused")):
                with self.assertRaisesRegex(RuntimeError, "ollama serve"):
                    ext.extract(img)

    def test_missing_model_points_at_pull(self):
        ext = GlimmerExtractor()
        err = _http_error(404, b'{"error": "model not found"}')
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"), _jpg_bytes(8, 8))
            with mock.patch("ptl.adapters.glimmer.urllib.request.urlopen",
                            side_effect=err):
                with self.assertRaisesRegex(RuntimeError, "ollama pull"):
                    ext.extract(img)

    def test_other_http_reraised(self):
        ext = GlimmerExtractor()
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"), _jpg_bytes(8, 8))
            with mock.patch("ptl.adapters.glimmer.urllib.request.urlopen",
                            side_effect=_http_error(500)):
                with self.assertRaises(urllib.error.HTTPError):
                    ext.extract(img)

    def test_four_pass_merge(self):
        header = dict(fresh(), line_items=[])
        header["issuer"] = dict(header["issuer"], tax_id="0105527027239")
        lines = {"line_items": [{"description": "L", "line_total": 100,
                                  "quantity": 1}]}
        dates = {"dates": {"issue_date": "2026-08-29",
                           "raw_date_string": "29/08/2026"}}
        form = {"form": "abbreviated", "can_claim_input_vat": False}
        opener = mock.MagicMock(side_effect=[
            _chat_ok(json.dumps(header))(), _chat_ok(json.dumps(lines))(),
            _chat_ok(json.dumps(dates))(), _chat_ok(json.dumps(form))()])
        ext = GlimmerExtractor()
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"), _jpg_bytes(8, 8))
            with mock.patch("ptl.adapters.glimmer.urllib.request.urlopen",
                            opener):
                doc, conf = ext.extract(img)
        self.assertEqual(opener.call_count, 4)
        prompts = [json.loads(call[0][0].data)["messages"][0]["content"]
                   for call in opener.call_args_list]
        self.assertEqual(prompts, [HEADER_PROMPT, LINES_PROMPT, DATES_PROMPT,
                                   FORM_PROMPT])
        self.assertEqual(doc["issuer"]["tax_id"], "0105527027239")
        self.assertEqual([li["description"] for li in doc["line_items"]],
                         ["L"])
        self.assertEqual(doc["dates"]["issue_date"], "2026-08-29")
        self.assertEqual(doc["form"], "abbreviated")
        self.assertFalse(doc["can_claim_input_vat"])
        self.assertEqual(conf, {})

    def test_dedicated_passes_own_their_sections(self):
        header = dict(fresh(), line_items=[{"description": "H",
                                             "line_total": 1}],
                      dates={"issue_date": "2000-01-01"}, form="full",
                      can_claim_input_vat=True)
        lines = {"line_items": [{"description": "L", "line_total": 2}]}
        dates = {"dates": {"issue_date": "2026-08-29"}}
        form = {"form": "abbreviated", "can_claim_input_vat": False}
        opener = mock.MagicMock(side_effect=[
            _chat_ok(json.dumps(header))(), _chat_ok(json.dumps(lines))(),
            _chat_ok(json.dumps(dates))(), _chat_ok(json.dumps(form))()])
        ext = GlimmerExtractor()
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"), _jpg_bytes(8, 8))
            with mock.patch("ptl.adapters.glimmer.urllib.request.urlopen",
                            opener):
                doc, _ = ext.extract(img)
        self.assertEqual([li["description"] for li in doc["line_items"]],
                         ["L"])
        self.assertEqual(doc["dates"]["issue_date"], "2026-08-29")
        self.assertEqual(doc["form"], "abbreviated")
        self.assertFalse(doc["can_claim_input_vat"])

    def test_merged_doc_infers_missing_subtotal(self):
        # Header owns totals but omits subtotal; the finalize build
        # recovers it from the merged lines via R1's equation.
        header = {"totals": {"grand_total": 3200}}
        lines = {"line_items": [{"description": "L", "line_total": 3200}]}
        opener = mock.MagicMock(side_effect=[
            _chat_ok(json.dumps(header))(), _chat_ok(json.dumps(lines))(),
            _chat_ok(json.dumps({}))(), _chat_ok(json.dumps({}))()])
        ext = GlimmerExtractor()
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"), _jpg_bytes(8, 8))
            with mock.patch("ptl.adapters.glimmer.urllib.request.urlopen",
                            opener):
                doc, _ = ext.extract(img)
        self.assertEqual(doc["totals"]["subtotal"], 3200)

    def test_single_pass_opt_out(self):
        ext = GlimmerExtractor()
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"), _jpg_bytes(8, 8))
            opener = _chat_ok(json.dumps(fresh()))
            with mock.patch("ptl.adapters.glimmer.urllib.request.urlopen",
                            opener):
                doc, _ = ext.extract(img, single_pass=True)
        self.assertEqual(opener.call_count, 1)
        self.assertEqual(
            json.loads(opener.call_args[0][0].data)["messages"][0]["content"],
            EXTRACTION_PROMPT)
        self.assertEqual(doc["totals"]["grand_total"], 10700)

    def test_header_prompt_pins_issuer_guidance(self):
        # S1 Glimmer emitted shop code 2083 plus a branch-suffixed
        # legal name; the guidance recovers 00031 plus the clean
        # registered name. Live obedience is verified by
        # re-extraction, not this pin.
        self.assertIn("not a shop code printed with", HEADER_PROMPT)
        self.assertIn("without any branch suffix", HEADER_PROMPT)

    def test_image_uri_stamped_from_path(self):
        ext = GlimmerExtractor()
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "receipt-9.jpg"),
                         _jpg_bytes(8, 8))
            with mock.patch("ptl.adapters.glimmer.urllib.request.urlopen",
                            _chat_repeat(json.dumps(fresh()))):
                doc, _ = ext.extract(img)
        self.assertEqual(doc["source"]["image_uri"], "receipt-9.jpg")

    def test_image_uri_absent_for_bytes(self):
        skel = {"schema_version": "1.0", "document_type": "receipt",
                "totals": {"grand_total": 100}}
        ext = GlimmerExtractor()
        with mock.patch("ptl.adapters.glimmer.urllib.request.urlopen",
                        _chat_repeat(json.dumps(skel))):
            doc, _ = ext.extract(_jpg_bytes(8, 8))
        self.assertNotIn("image_uri", doc["source"])

    def test_reviewer_delegates_to_triage(self):
        doc = fresh()
        v = validate(doc)
        self.assertEqual(GlimmerReviewer().review(doc, v), triage(doc, v))


if __name__ == "__main__":
    unittest.main()
