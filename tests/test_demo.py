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


if __name__ == "__main__":
    unittest.main()
