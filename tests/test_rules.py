import unittest

from ptl.pipeline.triage import triage
from ptl.pipeline.validate_rules import (thai_tax_id_check, validate,
                                          HARD_RULES)
from tests.fixtures import fresh


class TestRules(unittest.TestCase):
    def test_golden_passes(self):
        v = validate(fresh())
        self.assertFalse(v["requires_human_review"], v["review_reasons"])
        self.assertEqual(v["hard_failed"], [])

    def test_r1_line_mismatch(self):
        d = fresh()
        d["line_items"][0]["line_total"] = 1
        v = validate(d)
        self.assertFalse(v["rules"]["R1"]["pass"])
        self.assertIn("R1", v["hard_failed"])

    def test_r1_rounding_adjustment(self):
        # Lines sum to 10700; a -7 rounding line reconciles 10693.
        d = fresh()
        d["totals"]["rounding_adjustment"] = -7
        d["totals"]["subtotal"] = 10693
        v = validate(d)
        self.assertTrue(v["rules"]["R1"]["pass"], v["rules"]["R1"])
        # Control: without the term the same subtotal must fail.
        d2 = fresh()
        d2["totals"]["subtotal"] = 10693
        v2 = validate(d2)
        self.assertFalse(v2["rules"]["R1"]["pass"])

    def test_r3_wrong_vat(self):
        d = fresh()
        d["totals"]["vat_amount"] = 1
        v = validate(d)
        self.assertFalse(v["rules"]["R3"]["pass"])

    def test_r5_payment_mismatch(self):
        d = fresh()
        d["payments"] = [{"amount": 1, "method": "cash"}]
        v = validate(d)
        self.assertFalse(v["rules"]["R5"]["pass"])

    def test_r6_bad_checksum(self):
        self.assertTrue(thai_tax_id_check("1234567890121"))
        d = fresh()
        d["issuer"]["tax_id"] = "1234567890129"
        v = validate(d)
        self.assertFalse(v["rules"]["R6"]["pass"])

    def test_r7_future_date(self):
        d = fresh()
        d["dates"]["issue_date"] = "2999-01-01"
        v = validate(d)
        self.assertFalse(v["rules"]["R7"]["pass"])

    def test_r7_ambiguous_era_no_anchor(self):
        d = fresh()
        d["dates"]["era_resolution"] = {"detected_era": "ambiguous",
                                        "year_digits": 2,
                                        "anchor_used": None}
        v = validate(d)
        self.assertFalse(v["rules"]["R7"]["pass"])

    def test_r8_orphan_modifier(self):
        d = fresh()
        d["line_items"][1]["parent_line_number"] = 99
        v = validate(d)
        self.assertFalse(v["rules"]["R8"]["pass"])

    def test_r9_unflagged_subtotal(self):
        d = fresh()
        d["line_items"].append({"line_number": 4, "description": "Subtotal food",
                               "line_total": 8000})
        v = validate(d)
        self.assertFalse(v["rules"]["R9"]["pass"])

    def test_r10_duplicate(self):
        d = fresh()
        seen = {"doc_keys": {("1234567890121", "ABB-0001")},
                "fuzzy_keys": set(), "image_hashes": set()}
        v = validate(d, seen)
        self.assertFalse(v["rules"]["R10"]["pass"])

    def test_r11_placeholder_email(self):
        d = fresh()
        d["issuer"]["email"] = "noemail@example.com"
        v = validate(d)
        self.assertFalse(v["rules"]["R11"]["pass"])

    def test_r11_bad_branch(self):
        d = fresh()
        d["issuer"]["branch_code"] = "12"
        v = validate(d)
        self.assertFalse(v["rules"]["R11"]["pass"])

    def test_r11_four_digit_branch_ok(self):
        # CP Axtra/Lotus's slips print 4-digit store codes (S2 "1681").
        for code in ("1681", "00031"):
            d = fresh()
            d["issuer"]["branch_code"] = code
            v = validate(d)
            self.assertTrue(v["rules"]["R11"]["pass"])

    def test_r12_low_confidence(self):
        d = fresh()
        d["field_confidence"]["totals.vat_amount"] = 0.1
        v = validate(d)
        self.assertFalse(v["rules"]["R12"]["pass"])

    def test_hard_rules_set(self):
        self.assertEqual(HARD_RULES, {"R1", "R2", "R3", "R4", "R5", "R6"})

    def test_r13_empty_extraction_reviews(self):
        v = validate({})
        self.assertFalse(v["rules"]["R13"]["pass"])
        self.assertTrue(v["requires_human_review"])
        self.assertEqual(v["hard_failed"], [])  # soft: review, not block
        self.assertEqual(triage({}, v)["decision"], "needs_review")

    def test_r13_each_prong(self):
        def base():
            return {"totals": {"grand_total": 10700},
                    "line_items": [{"line_number": 1, "description": "x",
                                    "line_total": 10700}],
                    "dates": {"issue_date": "2026-08-27"}}
        cases = {"zero grand": {"totals": {"grand_total": 0}},
                 "no lines": {"line_items": []},
                 "no date": {"dates": {}}}
        for name, patch in cases.items():
            with self.subTest(name):
                doc = base()
                doc.update(patch)
                v = validate(doc)
                failed = [r for r, res in v["rules"].items()
                          if not res["pass"]]
                self.assertEqual(failed, ["R13"])
                self.assertTrue(v["requires_human_review"])


if __name__ == "__main__":
    unittest.main()
