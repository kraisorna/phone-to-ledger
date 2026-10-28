import unittest

from eval.score import aggregate, score_doc
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


if __name__ == "__main__":
    unittest.main()
