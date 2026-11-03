import argparse
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from ptl.eval.run_eval import load_labels, run_eval, write_labels
from ptl.eval.score import aggregate, normalise_legal, score_doc
from ptl.api.cli import cmd_eval, cmd_labels
from ptl.pipeline.triage import triage
from ptl.pipeline.validate_rules import validate
from tests.fixtures import SEEDS, fresh, fresh_seed


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

    def test_seed_triage_split(self):
        # The 25 seeds hold a 14-auto / 11-flag split through
        # validate+triage. Pin both directions: a rule change that
        # silently auto-accepts a bad seed or newly flags a good one
        # must fail loudly here, not drift the eval baseline.
        auto, flag = [], []
        for key in sorted(SEEDS):
            doc = fresh_seed(key)
            t = triage(doc, validate(doc))
            (auto if t["decision"] == "auto_accept" else flag).append(key)
        self.assertEqual(auto, ["S1", "S10", "S13", "S14", "S15", "S16",
                                "S18", "S19", "S2", "S22", "S5", "S6",
                                "S7", "S9"])
        self.assertEqual(flag, ["S11", "S12", "S17", "S20", "S21", "S23",
                                "S24", "S25", "S3", "S4", "S8"])

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

    def test_eval_ships_inside_package(self):
        import ptl
        import ptl.eval.run_eval
        import ptl.eval.score
        pkg = os.path.dirname(ptl.__file__)
        for mod in (ptl.eval.run_eval, ptl.eval.score):
            self.assertTrue(
                mod.__file__.startswith(pkg + os.sep),
                f"{mod.__name__} resolves outside the ptl package")

    def test_review_crosstab(self):
        # 05 sec 8 items 4-5: review rate, auto-accept accuracy,
        # flag recall — computed from the same validate+triage the
        # pipeline runs, no API.
        def _doc():
            return json.loads(json.dumps(fresh()))

        gold, preds = {}, {}
        for i in ("d1", "d2", "d3"):
            gold[i] = _doc()
        preds["d1"] = _doc()  # exact: correct + auto
        preds["d2"] = _doc()
        preds["d2"]["line_items"][0]["line_total"] += 100  # R1: wrong+flag
        preds["d3"] = _doc()
        preds["d3"]["issuer"]["legal_name"] = "Wrong Name"  # wrong, unflagged
        with tempfile.TemporaryDirectory() as tmp:
            labels = os.path.join(tmp, "labels")
            write_labels(labels, gold)
            path = os.path.join(tmp, "preds.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(preds, f)
            report = run_eval(path, labels)
        review = report["review"]
        self.assertEqual(review["n"], 3)
        self.assertEqual(review["flagged"], 1)
        self.assertAlmostEqual(review["review_rate"], 1 / 3)
        self.assertEqual(review["auto_accepted"], 2)
        self.assertEqual(review["auto_accept_all_correct"], 1)
        self.assertAlmostEqual(review["auto_accept_accuracy"], 0.5)
        self.assertEqual(review["wrong"], 2)
        self.assertEqual(review["wrong_flagged"], 1)
        self.assertAlmostEqual(review["flag_recall"], 0.5)
        self.assertEqual(review["flagged_ids"], ["d2"])
        self.assertEqual(review["wrong_unflagged_ids"], ["d3"])

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


class TestWriteLabels(unittest.TestCase):
    def test_roundtrip_and_determinism(self):
        # Labels regenerate byte-identically from the seeds, and
        # load straight back for the eval runner.
        with tempfile.TemporaryDirectory() as tmp:
            first = os.path.join(tmp, "a")
            write_labels(first, SEEDS)
            self.assertEqual(sorted(os.listdir(first)),
                             [f"{n}.json" for n in sorted(SEEDS)])
            back = load_labels(first)
            self.assertEqual(set(back), set(SEEDS))
            self.assertEqual(back["S1"], fresh_seed("S1"))
            second = os.path.join(tmp, "b")
            write_labels(second, SEEDS)
            for name in os.listdir(first):
                with open(os.path.join(first, name),
                          encoding="utf-8") as f:
                    a = f.read()
                with open(os.path.join(second, name),
                          encoding="utf-8") as f:
                    self.assertEqual(f.read(), a)

    def test_self_eval_all_correct(self):
        # Seeds scored against their own labels dump: the harness
        # end of the pipe, green by construction.
        with tempfile.TemporaryDirectory() as tmp:
            labels = os.path.join(tmp, "labels")
            write_labels(labels, SEEDS)
            preds = os.path.join(tmp, "preds.json")
            with open(preds, "w", encoding="utf-8") as f:
                json.dump({n: fresh_seed(n) for n in SEEDS}, f)
            faded = os.path.join(tmp, "faded.txt")
            with open(faded, "w", encoding="utf-8") as f:
                f.write("S5\nS17\n")
            report = run_eval(preds, labels, faded)
            self.assertEqual(report["overall"]["n"], len(SEEDS))
            self.assertEqual(report["overall"]["doc_all_correct"],
                             len(SEEDS))
            self.assertEqual(report["faded"]["n"], 2)
            self.assertEqual(report["missing_preds"], [])

    def test_cmd_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "labels")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_labels(argparse.Namespace(out=out))
            self.assertEqual(rc, 0)
            summary = json.loads(buf.getvalue())
            self.assertEqual(summary["labels"], len(SEEDS))
            self.assertEqual(load_labels(out)["S24"],
                             fresh_seed("S24"))


class TestNormaliseLegal(unittest.TestCase):
    # 05 sec 8 metric table: seller legal name is "exact after
    # normalisation (whitespace, Co.,Ltd. variants)". Punctuation,
    # spacing, and spelled-out spellings of the Latin limited-
    # suffix must fold; Thai legal forms (distinct company types)
    # and the name stem must not.
    def test_co_ltd_variants_fold(self):
        canon = normalise_legal("Thai yamazaki Co.,Ltd.")
        for v in ("Thai yamazaki Co., Ltd.",
                  "Thai yamazaki CO., LTD.",
                  "Thai yamazaki Company Limited",
                  "Thai yamazaki company limited"):
            self.assertEqual(normalise_legal(v), canon)

    def test_print_misprints_fold(self):
        self.assertEqual(
            normalise_legal("KAMRAIRUNGRUEANG 2022 CO..LTD"),
            normalise_legal("KAMRAIRUNGRUEANG 2022 CO.,LTD"))
        self.assertEqual(
            normalise_legal("MR. D.I.Y. (BANGKOK) CO,.LTD."),
            normalise_legal("MR. D.I.Y. (BANGKOK) Co., Ltd."))

    def test_thai_forms_and_stem_still_matter(self):
        self.assertNotEqual(
            normalise_legal("บมจ.ปตท. น้ำมันและการค้าปลีก"),
            normalise_legal("บจก.ปตท. น้ำมันและการค้าปลีก"))
        self.assertNotEqual(normalise_legal("Foo Co., Ltd."),
                            normalise_legal("Bar Co., Ltd."))
        self.assertNotEqual(
            normalise_legal("Thai yamazaki Co., Ltd."),
            normalise_legal("THAI YAMAZAKI Co., Ltd."))
        self.assertIsNone(normalise_legal(None))

    def test_seed_legal_variants_score(self):
        # S6/S9/S20 carry Latin Ltd suffixes; a pred that reads
        # the same suffix with different punctuation must score
        # the legal field, nothing else moving.
        variants = {
            "S6": "Thai yamazaki Co., Ltd.",
            "S9": "KAMRAIRUNGRUEANG 2022 CO.,LTD",
            "S20": "MR. D.I.Y. (BANGKOK) Co., Ltd.",
        }
        for key, name in variants.items():
            gold = fresh_seed(key)
            pred = fresh_seed(key)
            pred["issuer"]["legal_name"] = name
            s = score_doc(pred, gold)
            self.assertTrue(s["fields"]["issuer.legal_name"], key)
            self.assertTrue(s["all_correct"], key)


if __name__ == "__main__":
    unittest.main()
