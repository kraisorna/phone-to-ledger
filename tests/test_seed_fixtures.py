"""Seed fixtures S1-S6: edge-case catalogue as executable behaviour.

Each test pins a documented finding from 02-ocr-edge-cases.md to the
pipeline stage that must handle it (rules R1-R12, triage, scorer,
eval runner). Also smoke-tests eval/run_eval.py end to end.
"""
import json
import os
import tempfile
import unittest

from eval.run_eval import run_eval
from eval.score import score_doc
from ptl.pipeline.triage import triage
from ptl.pipeline.validate_rules import validate
from ptl.schema import check_structure
from tests.fixtures import SEEDS, fresh_seed


def failed_rules(validation):
    return sorted(r for r, v in validation["rules"].items()
                  if not v["pass"])


class TestSeedStructure(unittest.TestCase):
    def test_all_structurally_valid(self):
        for name in SEEDS:
            with self.subTest(seed=name):
                self.assertEqual(check_structure(fresh_seed(name)), [])

    def test_all_json_roundtrip(self):
        # Labels must survive a trip through data/labels + run_eval.
        for name in SEEDS:
            with self.subTest(seed=name):
                doc = fresh_seed(name)
                self.assertEqual(json.loads(json.dumps(doc)), doc)


class TestSeedRules(unittest.TestCase):
    def test_s2_absent_vat_skips_r3_r4(self):
        doc = fresh_seed("S2")
        self.assertIsNone(doc["totals"]["vat_amount"])
        v = validate(doc)
        self.assertTrue(v["rules"]["R3"]["pass"])
        self.assertTrue(v["rules"]["R4"]["pass"])
        self.assertEqual(failed_rules(v), [])
        self.assertFalse(v["requires_human_review"])
        self.assertEqual(triage(doc, v)["decision"], "auto_accept")

    def test_s2_embedded_qty_and_v_flag(self):
        lines = fresh_seed("S2")["line_items"]
        self.assertEqual(lines[0]["quantity"], 4)
        self.assertEqual(lines[0]["quantity_source"], "embedded_in_name")
        self.assertEqual(lines[1]["vat_flag"], "V")
        pay = fresh_seed("S2")["payments"][0]
        self.assertEqual(pay["card_mask_position"], "middle")

    def test_s3_placeholder_email_needs_review(self):
        doc = fresh_seed("S3")
        v = validate(doc)
        self.assertEqual(failed_rules(v), ["R11"])
        self.assertEqual(v["hard_failed"], [])
        self.assertTrue(v["requires_human_review"])
        self.assertEqual(triage(doc, v)["decision"], "needs_review")

    def test_s3_header_excluded_print_time_kept(self):
        doc = fresh_seed("S3")
        v = validate(doc)
        self.assertTrue(v["rules"]["R1"]["pass"])  # header not double-counted
        self.assertEqual(doc["dates"]["issue_date"], "2026-08-28")
        self.assertEqual(doc["dates"]["printed_at"], "2026-08-28T14:59:00")
        self.assertEqual(doc["qr_codes"][0]["purpose"], "feedback")

    def test_s4_anchorless_date_needs_review(self):
        doc = fresh_seed("S4")
        v = validate(doc)
        self.assertIn("R7", failed_rules(v))
        self.assertIn("ambiguous", v["rules"]["R7"]["detail"])
        self.assertTrue(v["requires_human_review"])
        # ...but the misaligned VAT still reconciles arithmetically.
        self.assertTrue(v["rules"]["R3"]["pass"])
        self.assertTrue(v["rules"]["R4"]["pass"])

    def test_s5_anchored_be_year_passes(self):
        doc = fresh_seed("S5")
        self.assertEqual(doc["dates"]["issue_date"], "2026-08-28")
        self.assertEqual(doc["dates"]["era_resolution"]["anchor_used"],
                         "TID#20260828")
        v = validate(doc)
        self.assertEqual(failed_rules(v), [])
        self.assertEqual(triage(doc, v)["decision"], "auto_accept")

    def test_s6_three_level_naming_passes(self):
        issuer = fresh_seed("S6")["issuer"]
        self.assertEqual(issuer["legal_name"], "Thai yamazaki Co.,Ltd.")
        self.assertEqual(issuer["brand_name"], "Saint Etoile")
        self.assertEqual(issuer["branch_code"], "00198")
        v = validate(fresh_seed("S6"))
        self.assertEqual(failed_rules(v), [])
        self.assertEqual(triage(fresh_seed("S6"), v)["decision"],
                         "auto_accept")


class TestS1CafeAmazon(unittest.TestCase):
    def test_split_payment_sums_to_total(self):
        doc = fresh_seed("S1")
        pays = doc["payments"]
        self.assertEqual([p["amount"] for p in pays], [3500, 1000])
        # The AIS 10 THB is tender, not a totals discount (the 02 section 5
        # trap: a parser grabbing the largest/last number gets 35.00).
        self.assertEqual(doc["totals"]["discount_total"], 0)
        self.assertEqual(doc["totals"]["grand_total"], 4500)
        self.assertTrue(validate(doc)["rules"]["R5"]["pass"])

    def test_modifier_attached(self):
        doc = fresh_seed("S1")
        mod = doc["line_items"][1]
        self.assertTrue(mod["is_modifier"])
        self.assertEqual(mod["parent_line_number"], 1)
        v = validate(doc)
        self.assertTrue(v["rules"]["R8"]["pass"])
        self.assertTrue(v["rules"]["R1"]["pass"])

    def test_printed_vatable_not_trusted(self):
        doc = fresh_seed("S1")
        # Slip prints "VATable: 45.00"; label carries recomputed 42.06.
        self.assertEqual(doc["totals"]["vatable_amount"], 4206)
        self.assertEqual(doc["totals"]["vat_amount"], 294)
        v = validate(doc)
        self.assertTrue(v["rules"]["R3"]["pass"])
        self.assertTrue(v["rules"]["R4"]["pass"])

    def test_full_pass_auto_accept(self):
        doc = fresh_seed("S1")
        self.assertEqual(doc["issuer"]["legal_name"],
                         "บมจ.ปตท. น้ำมันและการค้าปลีก")
        self.assertEqual(doc["issuer"]["brand_name"], "Cafe Amazon")
        v = validate(doc)
        self.assertEqual(failed_rules(v), [])
        self.assertEqual(triage(doc, v)["decision"], "auto_accept")


class TestSeedScoring(unittest.TestCase):
    def test_self_score_all_correct(self):
        for name in SEEDS:
            with self.subTest(seed=name):
                doc = fresh_seed(name)
                self.assertTrue(score_doc(doc, doc)["all_correct"])

    def test_run_eval_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            labels_d = os.path.join(tmp, "labels")
            os.mkdir(labels_d)
            preds = {}
            for name, doc in SEEDS.items():
                with open(os.path.join(labels_d, f"{name}.json"), "w",
                          encoding="utf-8") as f:
                    json.dump(doc, f, ensure_ascii=False)
                preds[name] = json.loads(json.dumps(doc))
            preds_p = os.path.join(tmp, "preds.json")
            with open(preds_p, "w", encoding="utf-8") as f:
                json.dump(preds, f)
            faded_p = os.path.join(tmp, "faded.txt")
            with open(faded_p, "w", encoding="utf-8") as f:
                f.write("S5\n")
            report = run_eval(preds_p, labels_d, faded_p)
            self.assertEqual(report["overall"]["n"], 6)
            self.assertEqual(report["overall"]["doc_all_correct"], 6)
            # S2 has no VAT line: totals.vat_amount scores over 5 docs, not 6.
            overall = report["overall"]
            self.assertEqual(overall["per_field_n"]["totals.vat_amount"], 5)
            self.assertEqual(overall["per_field_counts"]["totals.vat_amount"], 5)
            self.assertEqual(overall["per_field_n"]["totals.grand_total"],
                             6)
            self.assertEqual(report["missing_preds"], [])
            self.assertEqual(report["faded"]["n"], 1)
            self.assertEqual(report["faded"]["doc_all_correct"], 1)
            # A degraded pred must show up in per-field counts.
            preds["S2"]["totals"]["grand_total"] = 1
            with open(preds_p, "w", encoding="utf-8") as f:
                json.dump(preds, f)
            report = run_eval(preds_p, labels_d, faded_p)
            self.assertEqual(report["overall"]["doc_all_correct"], 5)
            counts = report["overall"]["per_field_counts"]
            self.assertEqual(counts["totals.grand_total"], 5)


if __name__ == "__main__":
    unittest.main()
