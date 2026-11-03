"""Demo assets stay in sync with the fixtures and exporter.

DEMO.md's script runs against demo/: if a fixture or the exporter
changes, the demo files must be regenerated, not left stale.
"""
import csv
import json
import os
import unittest

from ptl.pipeline.export import COLUMNS, to_csv, to_row
from ptl.pipeline.triage import triage
from ptl.pipeline.validate_rules import validate
from tests.fixtures import fresh_seed

DEMO = os.path.join(os.path.dirname(__file__), "..", "demo")


def demo_path(name):
    return os.path.join(DEMO, name)


class TestDemoAssets(unittest.TestCase):
    def test_sample_receipt_present(self):
        path = demo_path("sample.jpg")
        self.assertTrue(os.path.isfile(path))
        self.assertGreater(os.path.getsize(path), 100_000)

    def test_s1_json_matches_fixture(self):
        with open(demo_path("s1.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), fresh_seed("S1"))

    def test_expected_csv_matches_exporter(self):
        doc = fresh_seed("S1")
        status = triage(doc, validate(doc))["decision"]
        with open(demo_path("expected.csv"), encoding="utf-8") as f:
            want = to_csv([to_row(doc, review_status=status)])
            self.assertEqual(f.read().replace("\r\n", "\n"),
                             want.replace("\r\n", "\n"))

    def test_expected_csv_header_is_spec_columns(self):
        with open(demo_path("expected.csv"), encoding="utf-8") as f:
            self.assertEqual(next(csv.reader(f)), COLUMNS)

    def test_bad_sum_fails_r1(self):
        with open(demo_path("bad_sum.json"), encoding="utf-8") as f:
            v = validate(json.load(f))
        self.assertFalse(v["rules"]["R1"]["pass"])
        self.assertIn("R1", v["hard_failed"])

    def test_recorded_run_matches_current_schema(self):
        # demo/recorded_run.txt is the no-network fallback: a good live
        # capture that must show what the current CLI prints, never a
        # stale schema (it once showed the pre-strip Pillow note with no
        # review_enqueued key).
        with open(demo_path("recorded_run.txt"), encoding="utf-8") as f:
            text = f.read()
        start = text.index("{")
        rec, _ = json.JSONDecoder().raw_decode(text[start:])
        self.assertTrue(rec["ingest"]["exif_stripped"])  # sample.jpg
        self.assertIn("review_enqueued", rec)
        self.assertIn("attempts", rec["docs"][0])
        self.assertIn("partial", rec["crops"][0])
        self.assertIn("usage", rec)
        self.assertIn("estimated_usd_total", rec["usage"])
        self.assertIn("estimated_thb_total", rec["usage"])
        self.assertIn("estimated_thb", rec["usage"]["extract"])
        self.assertIn("elapsed_seconds", rec)
        self.assertEqual(rec["docs"][0]["triage"]["decision"], "auto_accept")
        row = rec["rows"][0]
        with open(demo_path("expected.csv"), encoding="utf-8") as f:
            exp = next(csv.DictReader(f))
        for key in exp:
            if key != "source_image_ref":
                self.assertEqual(str(row[key]), str(exp[key]), key)

    def test_review_seed_matches_bad_sum(self):
        # demo/review/bad_sum.json is the trust beat's pending
        # record: it must equal a fresh enqueue of bad_sum.json,
        # never a hand-edited stale copy.
        with open(demo_path("bad_sum.json"), encoding="utf-8") as f:
            doc = json.load(f)
        with open(demo_path("review/bad_sum.json"),
                  encoding="utf-8") as f:
            rec = json.load(f)
        v = validate(doc)
        self.assertEqual(rec["doc"], doc)
        self.assertEqual(rec["validation"], v)
        self.assertEqual(rec["triage"], triage(doc, v))
        self.assertEqual(rec["status"], "pending")
        self.assertEqual(rec["triage"]["decision"], "needs_review")


if __name__ == "__main__":
    unittest.main()
