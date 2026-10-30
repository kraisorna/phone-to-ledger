"""End-to-end wiring: segment -> extract -> validate -> triage -> rows.

Adapters are faked; no API calls. Covers the happy path, no-crop,
bad-doc, structurally-invalid, and duplicate-collapse paths, plus the
`ptl e2e` CLI plumbing with run_e2e mocked.
"""
import copy
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from ptl.api.cli import build_parser, cmd_e2e
from ptl.api.e2e import NO_RECEIPTS, run_e2e
from ptl.pipeline.dedup import SeenStore
from ptl.pipeline.segment import Crop
from tests.fixtures import fresh_seed

IMG = b"\xff\xd8\xff fake jpeg bytes"


def _crop(i=0):
    return Crop(index=i, polygon=[[0, 0], [10, 0], [10, 10], [0, 10]],
                image_path="s.jpg")


class _Seg:
    def __init__(self, crops):
        self._crops = crops

    def segment(self, image_path):
        return list(self._crops)


class _Ext:
    def __init__(self, docs):
        self._docs = docs
        self.calls = 0

    def extract(self, crop):
        doc = copy.deepcopy(self._docs[min(self.calls, len(self._docs) - 1)])
        self.calls += 1
        return doc, {}


def _image_file(data=IMG):
    f = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    f.write(data)
    f.close()
    return f.name


class TestRunE2E(unittest.TestCase):
    def test_happy_path_s1(self):
        path = _image_file()
        try:
            res = run_e2e(path, segmenter=_Seg([_crop()]),
                          extractor=_Ext([fresh_seed("S1")]))
        finally:
            os.unlink(path)
        self.assertEqual(len(res["crops"]), 1)
        self.assertEqual(len(res["rows"]), 1)
        self.assertEqual(res["rows"][0]["review_status"], "auto_accept")
        self.assertEqual(res["docs"][0]["triage"]["decision"], "auto_accept")
        self.assertIn("grand_total", res["csv"])
        self.assertEqual(res["docs"][0]["doc"]["source"]["crop_index"], 0)

    def test_no_crops(self):
        path = _image_file()
        try:
            res = run_e2e(path, segmenter=_Seg([]), extractor=_Ext([]))
        finally:
            os.unlink(path)
        self.assertEqual(res["note"], NO_RECEIPTS)
        self.assertEqual(res["rows"], [])
        self.assertEqual(res["docs"], [])

    def test_hard_fail_blocked_but_exported(self):
        doc = fresh_seed("S1")
        doc["line_items"][0]["line_total"] += 100  # break R1 (hard)
        path = _image_file()
        try:
            res = run_e2e(path, segmenter=_Seg([_crop()]),
                          extractor=_Ext([doc]))
        finally:
            os.unlink(path)
        entry = res["docs"][0]
        self.assertFalse(entry["validation"]["rules"]["R1"]["pass"])
        self.assertEqual(entry["triage"]["decision"], "needs_review")
        self.assertEqual(len(res["rows"]), 1)
        self.assertEqual(res["rows"][0]["review_status"], "blocked:R1")

    def test_soft_fail_needs_review(self):
        doc = fresh_seed("S1")
        doc["form"] = "unknown"  # break R14 (soft)
        path = _image_file()
        try:
            res = run_e2e(path, segmenter=_Seg([_crop()]),
                          extractor=_Ext([doc]))
        finally:
            os.unlink(path)
        entry = res["docs"][0]
        self.assertFalse(entry["validation"]["rules"]["R14"]["pass"])
        self.assertEqual(entry["triage"]["decision"], "needs_review")
        self.assertEqual(res["rows"][0]["review_status"], "needs_review")

    def test_struct_invalid_doc_excluded(self):
        doc = fresh_seed("S1")
        del doc["totals"]  # required top-level key
        path = _image_file()
        try:
            res = run_e2e(path, segmenter=_Seg([_crop()]),
                          extractor=_Ext([doc]))
        finally:
            os.unlink(path)
        self.assertTrue(res["docs"][0]["structure_errors"])
        self.assertTrue(res["docs"][0]["excluded"])
        self.assertEqual(res["rows"], [])

    def test_identical_crops_collapse_in_run(self):
        path = _image_file()
        try:
            res = run_e2e(path,
                          segmenter=_Seg([_crop(0), _crop(1)]),
                          extractor=_Ext([fresh_seed("S1")]))
        finally:
            os.unlink(path)
        self.assertEqual(len(res["rows"]), 1)
        self.assertTrue(res["docs"][1]["excluded"].startswith("duplicate"))

    def test_seen_store_flags_repeat(self):
        store = SeenStore()
        store.record(fresh_seed("S1"))
        path = _image_file()
        try:
            res = run_e2e(path, segmenter=_Seg([_crop()]),
                          extractor=_Ext([fresh_seed("S1")]),
                          seen_store=store)
        finally:
            os.unlink(path)
        self.assertEqual(res["rows"], [])
        self.assertIn("duplicate", res["docs"][0]["excluded"])


class TestCmdE2E(unittest.TestCase):
    def _args(self, **kw):
        base = {"image": "s.jpg", "out": "", "csv": "", "append": False,
                "seen": "", "concept": "receipt", "api_key": ""}
        base.update(kw)
        return mock.Mock(**base)

    def _result(self, **kw):
        res = {"image": "s.jpg", "ingest": {}, "crops": [{}],
               "docs": [{"triage": {"decision": "auto_accept"},
                         "excluded": ""}],
               "rows": [{"grand_total": "45.00"}], "csv": "h\nr\n",
               "note": ""}
        res.update(kw)
        return res

    def test_exit_0_and_csv_file(self):
        args = self._args(csv=os.path.join(tempfile.mkdtemp(), "l.csv"))
        with mock.patch("ptl.api.cli.run_e2e",
                         return_value=self._result()) as m:
            with mock.patch("sys.stdout", new_callable=io.StringIO):
                rc = cmd_e2e(args)
        self.assertEqual(rc, 0)
        m.assert_called_once()
        with open(args.csv, encoding="utf-8") as f:
            self.assertEqual(f.read(), "h\nr\n")

    def test_exit_2_needs_review(self):
        res = self._result(
            docs=[{"triage": {"decision": "needs_review"}, "excluded": ""}])
        args = self._args()
        with mock.patch("ptl.api.cli.run_e2e", return_value=res):
            with mock.patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(cmd_e2e(args), 2)

    def test_exit_3_no_rows(self):
        res = self._result(rows=[], csv="h\n", docs=[])
        args = self._args()
        with mock.patch("ptl.api.cli.run_e2e", return_value=res):
            with mock.patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(cmd_e2e(args), 3)

    def test_exit_4_no_receipts(self):
        res = self._result(rows=[], csv="h\n", docs=[], note=NO_RECEIPTS)
        args = self._args()
        with mock.patch("ptl.api.cli.run_e2e", return_value=res):
            with mock.patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(cmd_e2e(args), 4)

    def test_parser_wires_e2e(self):
        args = build_parser().parse_args(["e2e", "s.jpg"])
        self.assertEqual(args.func, cmd_e2e)
        self.assertEqual(args.concept, "receipt")


if __name__ == "__main__":
    unittest.main()
