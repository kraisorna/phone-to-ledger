"""SAM 3.1 adapter: grammar parsing + request contract (HTTP mocked).

Live behaviour (box frame == JPEG pixels, empty text on no-match) was
verified against api.meta.ai; these tests pin the parsing and error
paths without spending API calls.
"""
import io
import json
import os
import tempfile
import unittest
import urllib.error
from unittest import mock

from ptl.adapters.sam31 import Sam31Segmenter

TEXT_TWO = ("<0f>0<|box;x1=10;y1=20;x2=110;y2=220;w=200;h=400|>"
            "<|mask;x=0;y=0;data=8,8,~abc|>"
            "<0f>1<|box;x1=120;y1=20;x2=190;y2=220;w=200;h=400|>")


def _doc(text):
    return {"output": [{"type": "message", "content": [
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


class TestSam31(unittest.TestCase):
    def test_boxes_become_crops(self):
        seg = Sam31Segmenter(api_key="k")
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"), b"fake-jpeg-bytes")
            with mock.patch("ptl.adapters.sam31.urllib.request.urlopen",
                            _urlopen_ok(_doc(TEXT_TWO))):
                crops = seg.segment(img)
        self.assertEqual(len(crops), 2)
        self.assertEqual(crops[0].polygon,
                         [[10, 20], [110, 20], [110, 220], [10, 220]])
        self.assertEqual(crops[1].polygon,
                         [[120, 20], [190, 20], [190, 220], [120, 220]])
        self.assertFalse(crops[0].deskewed)
        self.assertFalse(crops[0].partial)

    def test_request_shape(self):
        seg = Sam31Segmenter(api_key="k", concept="receipt")
        opener = _urlopen_ok(_doc(""))
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"), b"fake-jpeg-bytes")
            with mock.patch("ptl.adapters.sam31.urllib.request.urlopen",
                            opener):
                seg.segment(img)
        (req,), _ = opener.call_args
        self.assertTrue(req.full_url.endswith("/responses"))
        payload = json.loads(req.data)
        self.assertEqual(payload["model"], "sam-3.1")
        self.assertFalse(payload["stream"])
        content = payload["input"][0]["content"]
        self.assertEqual(content[0]["text"], "receipt")
        self.assertTrue(content[1]["image_url"].startswith(
            "data:image/jpeg;base64,"))

    def test_empty_text_means_no_receipts(self):
        self.assertEqual(Sam31Segmenter.boxes_from_text(""), [])
        self.assertEqual(Sam31Segmenter.boxes_from_text("  \n "), [])

    def test_malformed_box_raises(self):
        bad = "<0f>0<|box;x1=50;y1=20;x2=10;y2=220;w=200;h=400|>"
        with self.assertRaises(ValueError):
            Sam31Segmenter.boxes_from_text(bad)

    def test_prose_without_grammar_raises(self):
        with self.assertRaises(ValueError):
            Sam31Segmenter.boxes_from_text("here is your segmentation")

    def test_missing_key_raises(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("MODEL_API_KEY", None)
            seg = Sam31Segmenter()
        with tempfile.TemporaryDirectory() as tmp:
            img = _write(os.path.join(tmp, "r.jpg"))
            with self.assertRaises(RuntimeError):
                seg.segment(img)

    def test_auth_and_entitlement_errors(self):
        seg = Sam31Segmenter(api_key="k")
        for code, hint in ((401, "401"), (404, "entitlement")):
            err = urllib.error.HTTPError(
                "https://api.meta.ai/v1/responses", code, "x", {}, None)
            with mock.patch("ptl.adapters.sam31.urllib.request.urlopen",
                            side_effect=err):
                with self.assertRaisesRegex(RuntimeError, hint):
                    with tempfile.TemporaryDirectory() as tmp:
                        img = _write(os.path.join(tmp, "r.jpg"))
                        seg.segment(img)


if __name__ == "__main__":
    unittest.main()
