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
        self.assertEqual(payload["temperature"], 0)
        fmt = payload["text"]["format"]
        self.assertEqual(fmt["type"], "json_schema")
        self.assertIn("totals", fmt["schema"]["properties"])
        content = payload["input"][0]["content"]
        self.assertTrue(content[1]["image_url"].startswith(
            "data:image/jpeg;base64,"))
        for phrase in ("satang", "YYYY-MM-DD", "recompute", "ambiguous"):
            self.assertIn(phrase, PROMPT)
            self.assertIn(phrase, content[0]["text"])

    def test_temperature_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"))
            opener = _urlopen_ok(_doc(json.dumps(fresh())))
            with mock.patch("ptl.adapters.spark.urllib.request.urlopen",
                            opener):
                SparkExtractor(api_key="k", temperature=1).extract(img)
            (req,), _ = opener.call_args
            self.assertEqual(json.loads(req.data)["temperature"], 1)
            opener = _urlopen_ok(_doc(json.dumps(fresh())))
            with mock.patch("ptl.adapters.spark.urllib.request.urlopen",
                            opener):
                SparkExtractor(api_key="k", temperature=None).extract(img)
            (req,), _ = opener.call_args
            self.assertNotIn("temperature", json.loads(req.data))

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

    def test_normalize_keys(self):
        messy = {"dates ": {"issue_date": "2026-08-28",
                            "era_resolution ": {"detected_era": "AD"}},
                 "totals": {"grand_total": 100},
                 "dup ": 1, "dup": 2}
        clean = SparkExtractor._normalize_keys(messy)
        self.assertEqual(clean["dates"]["issue_date"], "2026-08-28")
        self.assertEqual(clean["dates"]["era_resolution"]["detected_era"],
                         "AD")
        self.assertEqual(clean["dup"], 2)  # exact key wins
        self.assertIn("dates ", messy)  # input untouched

    def test_spaced_output_recovers(self):
        ext = SparkExtractor(api_key="k")
        text = json.dumps({"schema_version": "1.0",
                           "document_type": "combined",
                           "issuer ": {"tax_id": "1"},
                           "issuer": {"tax_id": "2"},
                           "totals ": {"grand_total": 5}})
        opener = _urlopen_ok(_doc(text))
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"))
            with mock.patch("ptl.adapters.spark.urllib.request.urlopen",
                            opener):
                doc, _ = ext.extract(img)
        self.assertEqual(doc["issuer"]["tax_id"], "2")
        self.assertEqual(doc["totals"]["grand_total"], 5)

    def test_input_kinds(self):
        ext = SparkExtractor(api_key="k")
        doc = _doc(json.dumps(fresh()))
        opener = mock.MagicMock(
            side_effect=lambda *a, **k: _urlopen_ok(doc)())
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
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"))
            with mock.patch.dict(os.environ), \
                    mock.patch("os.getcwd", return_value=tmp):
                os.environ.pop("MODEL_API_KEY", None)
                ext = SparkExtractor()
                with self.assertRaises(RuntimeError):
                    ext.extract(img)

    def test_dotenv_key_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, ".env"), "w",
                      encoding="utf-8") as f:
                f.write("MODEL_API_KEY=from-dotenv\n")
            with mock.patch.dict(os.environ), \
                    mock.patch("os.getcwd", return_value=tmp):
                os.environ.pop("MODEL_API_KEY", None)
                self.assertEqual(SparkExtractor().api_key, "from-dotenv")

    def test_transport_timeout_retried(self):
        ext = SparkExtractor(api_key="k")
        opener = mock.MagicMock(
            side_effect=[TimeoutError("The read operation timed out"),
                         _urlopen_ok(_doc(json.dumps(fresh())))()])
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"))
            with mock.patch("ptl.adapters.spark.urllib.request.urlopen",
                            opener), \
                    mock.patch("ptl.adapters.base.sleep"):
                doc, _ = ext.extract(img)
        self.assertEqual(doc["totals"]["grand_total"], 10700)
        self.assertEqual(opener.call_count, 2)

    def test_stats_accumulate(self):
        ext = SparkExtractor(api_key="k")
        body = _doc(json.dumps(fresh()))
        body["usage"] = {"input_tokens": 1200, "output_tokens": 300}
        opener = mock.MagicMock(
            side_effect=[_urlopen_ok(body)(), _urlopen_ok(body)()])
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"))
            with mock.patch("ptl.adapters.spark.urllib.request.urlopen",
                            opener):
                ext.extract(img)
                ext.extract(img)
        self.assertEqual(ext.stats["calls"], 2)
        self.assertEqual(ext.stats["input_tokens"], 2400)
        self.assertEqual(ext.stats["output_tokens"], 600)
        self.assertGreaterEqual(ext.stats["seconds"], 0)

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
