"""Muse Spark adapter: payload contract + parse/retry paths (HTTP mocked).

Live behaviour (schema-constrained JSON, reasoning item first) was
verified against api.meta.ai; these tests pin the parsing, retry, and
error paths without spending API calls.
"""
import io
import json
import os
import tempfile
import unittest
import urllib.error
from unittest import mock

from ptl.adapters.spark import MODEL, PROMPT, SparkExtractor
from ptl.pipeline.segment import Crop
from tests.fixtures import fresh


def _doc(text):
    return {"output": [
        {"type": "reasoning", "id": "r", "status": "done", "summary": []},
        {"type": "message", "content": [
            {"type": "output_text", "text": text}]}]}


def _urlopen_ok(doc):
    resp = mock.MagicMock()
    resp.__enter__.return_value = io.StringIO(json.dumps(doc))
    resp.__exit__.return_value = False
    return mock.MagicMock(return_value=resp)


def _write(path, data=b"x"):
    with open(path, "wb") as f:
        f.write(data)
    return path


class TestSpark(unittest.TestCase):
    def test_roundtrip(self):
        ext = SparkExtractor(api_key="k")
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"))
            with mock.patch("ptl.adapters.spark.urllib.request.urlopen",
                            _urlopen_ok(_doc(json.dumps(fresh())))):
                doc, conf = ext.extract(img)
        self.assertEqual(doc["totals"]["grand_total"], 10700)
        self.assertEqual(conf, {})
        self.assertEqual(doc["source"]["model"], MODEL)
        self.assertEqual(doc["source"]["kind"], "ocr")

    def test_request_shape(self):
        ext = SparkExtractor(api_key="k")
        opener = _urlopen_ok(_doc(json.dumps(fresh())))
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"))
            with mock.patch("ptl.adapters.spark.urllib.request.urlopen",
                            opener):
                ext.extract(img)
        (req,), _ = opener.call_args
        self.assertTrue(req.full_url.endswith("/responses"))
        payload = json.loads(req.data)
        self.assertEqual(payload["model"], MODEL)
        self.assertFalse(payload["stream"])
        fmt = payload["text"]["format"]
        self.assertEqual(fmt["type"], "json_schema")
        self.assertIn("totals", fmt["schema"]["properties"])
        content = payload["input"][0]["content"]
        self.assertTrue(content[1]["image_url"].startswith(
            "data:image/jpeg;base64,"))
        for phrase in ("satang", "YYYY-MM-DD", "recompute", "ambiguous"):
            self.assertIn(phrase, PROMPT)
            self.assertIn(phrase, content[0]["text"])

    def test_retry_then_success(self):
        ext = SparkExtractor(api_key="k")
        good = _urlopen_ok(_doc(json.dumps(fresh())))
        bad = _urlopen_ok(_doc("not json{{"))
        opener = mock.MagicMock(side_effect=[bad.return_value,
                                             good.return_value])
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"))
            with mock.patch("ptl.adapters.spark.urllib.request.urlopen",
                            opener):
                doc, _ = ext.extract(img)
        self.assertEqual(opener.call_count, 2)
        self.assertEqual(doc["totals"]["grand_total"], 10700)

    def test_persistent_garbage_raises(self):
        ext = SparkExtractor(api_key="k")
        opener = mock.MagicMock(
            side_effect=lambda *a, **k: _urlopen_ok(_doc("nope"))())
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"))
            with mock.patch("ptl.adapters.spark.urllib.request.urlopen",
                            opener):
                with self.assertRaises(ValueError):
                    ext.extract(img)
        self.assertEqual(opener.call_count, 2)

    def test_invalid_structure_returns_best_effort(self):
        ext = SparkExtractor(api_key="k")
        opener = mock.MagicMock(
            side_effect=lambda *a, **k: _urlopen_ok(_doc("{}"))())
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"))
            with mock.patch("ptl.adapters.spark.urllib.request.urlopen",
                            opener):
                doc, _ = ext.extract(img)
        self.assertEqual(opener.call_count, 2)
        self.assertEqual(doc["schema_version"], "1.0")  # build defaults

    def test_input_kinds(self):
        ext = SparkExtractor(api_key="k")
        opener = _urlopen_ok(_doc(json.dumps(fresh())))
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"), b"fake")
            with mock.patch("ptl.adapters.spark.urllib.request.urlopen",
                            opener):
                ext.extract(b"\xff\xd8\xff fake-jpeg")
                ext.extract(img)
                ext.extract(Crop(index=0, polygon=[], image_path=img))
            with self.assertRaises(ValueError):
                ext.extract(Crop(index=0, polygon=[]))
            with self.assertRaises(ValueError):
                ext.extract(b"not-an-image")

    def test_missing_key_raises(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("MODEL_API_KEY", None)
            ext = SparkExtractor()
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"))
            with self.assertRaises(RuntimeError):
                ext.extract(img)

    def test_auth_and_entitlement_errors(self):
        ext = SparkExtractor(api_key="k")
        for code, hint in ((401, "401"), (404, "entitlement")):
            err = urllib.error.HTTPError(
                "https://api.meta.ai/v1/responses", code, "x", {}, None)
            with mock.patch("ptl.adapters.spark.urllib.request.urlopen",
                            side_effect=err):
                with tempfile.TemporaryDirectory() as tmp:
                    img = _write(os.path.join(tmp, "r.jpg"))
                    with self.assertRaisesRegex(RuntimeError, hint):
                        ext.extract(img)


if __name__ == "__main__":
    unittest.main()
