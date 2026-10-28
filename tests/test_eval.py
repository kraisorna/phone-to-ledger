import argparse
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from eval.score import aggregate, score_doc
from ptl.api.cli import cmd_eval
from tests.fixtures import fresh


class TestEval(unittest.TestCase):
    def test_identical_all_correct(self):
        s = score_doc(fresh(), fresh())
        self.assertTrue(s["all_correct"])
        self.assertEqual(s["lines"]["f1"], 1.0)

    def test_wrong_money_fails(self):
        p = fresh()
        p["totals"]["grand_total"] = 1
        s = score_doc(p, fresh())
        self.assertFalse(s["all_correct"])
        self.assertFalse(s["fields"]["totals.grand_total"])

    def test_faded_split(self):
        ok = score_doc(fresh(), fresh())
        ok["doc_id"] = "s1"
        bad = score_doc({"totals": {"grand_total": 1}}, fresh())
        bad["doc_id"] = "s2"
        rep = aggregate([ok, bad], frozenset({"s2"}))
        self.assertEqual(rep["overall"]["n"], 2)
        self.assertEqual(rep["overall"]["doc_all_correct"], 1)
        self.assertEqual(rep["faded"]["n"], 1)
        self.assertEqual(rep["faded"]["doc_all_correct"], 0)

    def test_cmd_eval_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            labels = os.path.join(tmp, "labels")
            os.mkdir(labels)
            with open(os.path.join(labels, "d1.json"), "w",
                      encoding="utf-8") as f:
                json.dump(fresh(), f)
            preds = os.path.join(tmp, "preds.json")
            with open(preds, "w", encoding="utf-8") as f:
                json.dump({"d1": fresh()}, f)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_eval(argparse.Namespace(
                    preds=preds, labels=labels, faded_ids=""))
            self.assertEqual(rc, 0)
            report = json.loads(buf.getvalue())
            self.assertEqual(report["overall"]["doc_all_correct"], 1)


if __name__ == "__main__":
    unittest.main()
