"""Validation-guided extraction retry (scripted extractor, no API).

Live VLM reads flip run to run while the print stays fixed (S1 branch
00031/2083, S4 60G/GOG); a retry keeps the better reading. These tests
pin the mechanism with a scripted extractor and the real validator.
"""
import copy
import unittest

from ptl.pipeline.retry import retry_extract
from ptl.pipeline.triage import DECIDE_AUTO, DECIDE_REVIEW
from tests.fixtures import fresh_seed


def _break_grand(doc, marker):
    # Rules tolerate +-1 satang and ignore totals.total, so break the
    # checked grand_total by a wide, attempt-identifying margin.
    out = copy.deepcopy(doc)
    out["totals"]["grand_total"] = marker
    return out


def _break_tax_id(doc):
    out = copy.deepcopy(doc)
    tax = out["issuer"]["tax_id"]
    out["issuer"]["tax_id"] = tax[:-1] + ("0" if tax[-1] != "0" else "1")
    return out


class ScriptedExtractor:
    """extract(source) -> next scripted (doc, conf); repeats the last."""

    def __init__(self, docs):
        self.docs = docs
        self.calls = 0

    def extract(self, source):
        self.calls += 1
        return copy.deepcopy(self.docs[min(self.calls - 1,
                                           len(self.docs) - 1)]), {}


class TestRetryExtract(unittest.TestCase):
    def test_clean_first_attempt_never_retries(self):
        ex = ScriptedExtractor([fresh_seed("S1")])
        doc, conf, validation, decision, used = retry_extract("s1", ex)
        self.assertEqual(ex.calls, 1)
        self.assertEqual(used, 1)
        self.assertEqual(decision["decision"], DECIDE_AUTO)
        self.assertEqual(doc["totals"]["grand_total"], 4500)

    def test_retry_recovers_flagged_first_attempt(self):
        ex = ScriptedExtractor([_break_grand(fresh_seed("S1"), 4600),
                                fresh_seed("S1")])
        doc, conf, validation, decision, used = retry_extract("s1", ex)
        self.assertEqual(ex.calls, 2)
        self.assertEqual(used, 2)
        self.assertEqual(decision["decision"], DECIDE_AUTO)
        self.assertEqual(doc["totals"]["grand_total"], 4500)

    def test_persistent_failure_keeps_first_attempt(self):
        ex = ScriptedExtractor([_break_grand(fresh_seed("S1"), 4600),
                                _break_grand(fresh_seed("S1"), 4700)])
        doc, conf, validation, decision, used = retry_extract("s1", ex)
        self.assertEqual(used, 2)
        self.assertEqual(decision["decision"], DECIDE_REVIEW)
        self.assertEqual(doc["totals"]["grand_total"], 4600)

    def test_fewer_failures_wins(self):
        worse = _break_tax_id(_break_grand(fresh_seed("S1"), 4600))
        better = _break_grand(fresh_seed("S1"), 4700)
        ex = ScriptedExtractor([worse, better])
        doc, conf, validation, decision, used = retry_extract("s1", ex)
        self.assertEqual(doc["totals"]["grand_total"], 4700)
        self.assertEqual(decision["decision"], DECIDE_REVIEW)

    def test_retry_regression_keeps_first_attempt(self):
        better = _break_grand(fresh_seed("S1"), 4600)
        worse = _break_tax_id(_break_grand(fresh_seed("S1"), 4700))
        ex = ScriptedExtractor([better, worse])
        doc, conf, validation, decision, used = retry_extract("s1", ex)
        self.assertEqual(doc["totals"]["grand_total"], 4600)

    def test_retry_never_clears_a_failure(self):
        ex = ScriptedExtractor([_break_grand(fresh_seed("S1"), 4600),
                                _break_grand(fresh_seed("S1"), 4600)])
        doc, conf, validation, decision, used = retry_extract("s1", ex)
        failed = [r for r, v in validation["rules"].items()
                  if not v["pass"]]
        self.assertTrue(failed)
        self.assertEqual(decision["decision"], DECIDE_REVIEW)

    def test_attempts_floor_is_one(self):
        ex = ScriptedExtractor([fresh_seed("S1")])
        with self.assertRaises(ValueError):
            retry_extract("s1", ex, attempts=0)


if __name__ == "__main__":
    unittest.main()
