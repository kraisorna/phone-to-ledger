"""Baseline runner: systems A-D over an image dir -> preds JSON (mocked).

The mission compares the full pipeline against Thai Tesseract (A) and a
single-prompt baseline (B); these tests pin the runner shapes without
spending API calls or needing the tesseract binary.
"""
import argparse
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from ptl.api.cli import cmd_baseline
from ptl.eval import run_baseline


def _touch(path):
    with open(path, "wb") as f:
        f.write(b"x")
    return path


def _images(tmp, *names):
    d = os.path.join(tmp, "images")
    os.mkdir(d)
    for n in names:
        _touch(os.path.join(d, n))
    return d


class TestRunBaseline(unittest.TestCase):
    def test_single_doc_system(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _images(tmp, "S1.jpg", "S2.JPG", "notes.txt", ".DS_Store")
            systems = {"a": lambda p, **kw: {"doc": os.path.basename(p)}}
            with mock.patch.object(run_baseline, "SYSTEMS", systems):
                preds, summary = run_baseline.run_baseline("a", d)
        self.assertEqual(sorted(preds), ["S1", "S2"])
        self.assertEqual(preds["S1"], {"doc": "S1.jpg"})
        self.assertEqual(summary["images"], 2)
        self.assertEqual(summary["preds"], 2)
        self.assertEqual(summary["missing"], [])
        self.assertEqual(summary["errors"], {})

    def test_tuple_shape_unwrapped(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _images(tmp, "S1.jpg")
            systems = {"b": lambda p, **kw: ({"doc": 1}, {})}
            with mock.patch.object(run_baseline, "SYSTEMS", systems):
                preds, _ = run_baseline.run_baseline("b", d)
        self.assertEqual(preds, {"S1": {"doc": 1}})

    def test_single_accepted_crop_uses_stem(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _images(tmp, "S1.jpg")
            systems = {"c": lambda p, **kw: [
                {"crop": 0, "rejected": {"passed_gate": False}},
                {"crop": 1, "doc": {"doc": 1}}]}
            with mock.patch.object(run_baseline, "SYSTEMS", systems):
                preds, _ = run_baseline.run_baseline("c", d)
        self.assertEqual(preds, {"S1": {"doc": 1}})

    def test_multi_crop_keys_use_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _images(tmp, "S1.jpg")
            systems = {"c": lambda p, **kw: [
                {"crop": 0, "doc": {"doc": 0}},
                {"crop": 2, "doc": {"doc": 2}}]}
            with mock.patch.object(run_baseline, "SYSTEMS", systems):
                preds, _ = run_baseline.run_baseline("c", d)
        self.assertEqual(preds, {"S1#0": {"doc": 0}, "S1#2": {"doc": 2}})

    def test_rejected_only_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _images(tmp, "S1.jpg")
            systems = {"c": lambda p, **kw: [
                {"crop": 0, "rejected": {"passed_gate": False}}]}
            with mock.patch.object(run_baseline, "SYSTEMS", systems):
                preds, summary = run_baseline.run_baseline("c", d)
        self.assertEqual(preds, {})
        self.assertEqual(summary["missing"], ["S1"])

    def test_per_image_error_collected(self):
        def flaky(path, **kw):
            if "bad" in path:
                raise RuntimeError("boom")
            return {"doc": 1}

        with tempfile.TemporaryDirectory() as tmp:
            d = _images(tmp, "S1.jpg", "bad.jpg")
            with mock.patch.object(run_baseline, "SYSTEMS", {"a": flaky}):
                preds, summary = run_baseline.run_baseline("a", d)
        self.assertEqual(sorted(preds), ["S1"])
        self.assertEqual(list(summary["errors"]), ["bad"])
        self.assertIn("boom", summary["errors"]["bad"])

    def test_unknown_system(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _images(tmp, "S1.jpg")
            with self.assertRaises(ValueError):
                run_baseline.run_baseline("z", d)

    def test_registry_covers_abcd(self):
        self.assertEqual(sorted(run_baseline.SYSTEMS), ["a", "b", "c", "d"])

    def test_system_b_disables_postprocessing(self):
        from ptl.eval.baselines import b_spark_raw
        with mock.patch.object(b_spark_raw, "SparkExtractor") as cls:
            b_spark_raw.run("img.jpg", api_key="k")
        cls.assert_called_once_with(api_key="k")
        cls.return_value.extract.assert_called_once_with(
            "img.jpg", postprocess=False)


class TestBaselineCli(unittest.TestCase):
    def test_cmd_writes_preds_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _images(tmp, "S1.jpg")
            out = os.path.join(tmp, "preds.json")
            systems = {"a": lambda p, **kw: {"doc": 1}}
            buf = io.StringIO()
            with mock.patch.object(run_baseline, "SYSTEMS", systems), \
                    redirect_stdout(buf):
                rc = cmd_baseline(argparse.Namespace(
                    system="a", images=d, out=out))
            self.assertEqual(rc, 0)
            with open(out, encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"S1": {"doc": 1}})
            summary = json.loads(buf.getvalue())
            self.assertEqual(summary["preds"], 1)

    def test_cmd_exit_1_when_nothing_produced(self):
        def fail(path, **kw):
            raise RuntimeError("no weights")

        with tempfile.TemporaryDirectory() as tmp:
            d = _images(tmp, "S1.jpg")
            out = os.path.join(tmp, "preds.json")
            buf = io.StringIO()
            with mock.patch.object(run_baseline, "SYSTEMS", {"d": fail}), \
                    redirect_stdout(buf):
                rc = cmd_baseline(argparse.Namespace(
                    system="d", images=d, out=out))
            self.assertEqual(rc, 1)
            self.assertFalse(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
