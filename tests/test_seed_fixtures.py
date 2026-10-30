"""Seed fixtures S1-S6: edge-case catalogue as executable behaviour.

Each test pins a documented finding from 02-ocr-edge-cases.md to the
pipeline stage that must handle it (rules R1-R12, triage, scorer,
eval runner). Also smoke-tests eval/run_eval.py end to end.
"""
import json
import os
import tempfile
import unittest

from ptl.eval.run_eval import run_eval
from ptl.eval.score import score_doc
from ptl.pipeline.extract import normalise_pos_identifier
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

    def test_no_placeholder_filler(self):
        # Seeds double as eval gold: transcribed values only, never
        # "(name not transcribed)" style filler with fabricated splits.
        for name in SEEDS:
            with self.subTest(seed=name):
                text = json.dumps(fresh_seed(name), ensure_ascii=False)
                self.assertNotIn("not transcribed", text)


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
                         "TID#2026082800000005170679622")
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
        self.assertEqual(doc["issuer"]["tax_id"], "0107561000013")
        self.assertEqual(doc["issuer"]["branch_code"], "00031")
        self.assertEqual(doc["document_number"], "2083RC082569/005087")
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
            self.assertEqual(report["overall"]["n"], 12)
            self.assertEqual(report["overall"]["doc_all_correct"], 12)
            # S2 and S7-S9 have no VAT line: totals.vat_amount scores
            # over 8 docs.
            overall = report["overall"]
            self.assertEqual(overall["per_field_n"]["totals.vat_amount"], 8)
            self.assertEqual(overall["per_field_counts"]["totals.vat_amount"], 8)
            self.assertEqual(overall["per_field_n"]["totals.grand_total"],
                             12)
            self.assertEqual(report["missing_preds"], [])
            self.assertEqual(report["faded"]["n"], 1)
            self.assertEqual(report["faded"]["doc_all_correct"], 1)
            # A degraded pred must show up in per-field counts.
            preds["S2"]["totals"]["grand_total"] = 1
            with open(preds_p, "w", encoding="utf-8") as f:
                json.dump(preds, f)
            report = run_eval(preds_p, labels_d, faded_p)
            self.assertEqual(report["overall"]["doc_all_correct"], 11)
            counts = report["overall"]["per_field_counts"]
            self.assertEqual(counts["totals.grand_total"], 11)


class TestS22SevenSecondSlip(unittest.TestCase):
    def test_anchored_be_year_passes(self):
        doc = fresh_seed("S22")
        self.assertEqual(doc["dates"]["issue_date"], "2026-10-29")
        self.assertEqual(doc["dates"]["era_resolution"]["anchor_used"],
                         "TID#2026102900000005417306139")
        v = validate(doc)
        self.assertTrue(v["rules"]["R7"]["pass"])

    def test_stray_h_stripped_verbatim_kept(self):
        lines = fresh_seed("S22")["line_items"]
        self.assertEqual(lines[0]["description"], "วอลล์ 2in1 ช็อกโก")
        self.assertEqual(lines[0]["description_raw"], "Hวอลล์ 2in1 ช็อกโก")
        self.assertEqual(lines[1]["description"], "นมพาสฯเมจิ 450")
        self.assertTrue(lines[1]["description_raw"].startswith("H"))

    def test_branch_beats_vat_code_decoy(self):
        # (02304) with the store name is the branch; Vat Code 02314 is
        # a decoy in the next row, like S1's 00031-vs-2083 split.
        self.assertEqual(fresh_seed("S22")["issuer"]["branch_code"],
                         "02304")

    def test_computed_vat_no_printed_rows(self):
        doc = fresh_seed("S22")
        # No VATable/VAT rows on the slip: 505/7220 are computed.
        self.assertEqual(doc["totals"]["vat_amount"], 505)
        self.assertEqual(doc["totals"]["vatable_amount"], 7220)
        v = validate(doc)
        self.assertTrue(v["rules"]["R3"]["pass"])
        self.assertTrue(v["rules"]["R4"]["pass"])
        # Member points (+42/10469) must not leak into totals.
        self.assertEqual(doc["totals"]["grand_total"], 7725)
        self.assertTrue(v["rules"]["R5"]["pass"])

    def test_full_pass_auto_accept(self):
        doc = fresh_seed("S22")
        v = validate(doc)
        self.assertEqual(failed_rules(v), [])
        self.assertEqual(triage(doc, v)["decision"], "auto_accept")


class TestS21NoodleShopBill(unittest.TestCase):
    def test_unknown_form_is_only_failure(self):
        # No ABB/full marks anywhere: R14 must fire, alone and soft.
        doc = fresh_seed("S21")
        v = validate(doc)
        self.assertEqual(failed_rules(v), ["R14"])
        self.assertEqual(v["hard_failed"], [])
        self.assertEqual(triage(doc, v)["decision"], "needs_review")

    def test_count_row_is_not_a_line(self):
        lines = fresh_seed("S21")["line_items"]
        self.assertEqual(len(lines), 3)
        self.assertNotIn("จำนวน", "".join(
            li["description"] for li in lines))

    def test_unpaid_without_tender_passes_r5(self):
        doc = fresh_seed("S21")
        self.assertEqual(doc["payments"], [])
        self.assertEqual(doc["status"], "unpaid")
        v = validate(doc)
        self.assertTrue(v["rules"]["R5"]["pass"])

    def test_clean_vat_arithmetic_passes(self):
        doc = fresh_seed("S21")
        self.assertEqual(doc["totals"]["vat_amount"], 648)
        self.assertEqual(doc["totals"]["vatable_amount"], 9252)
        v = validate(doc)
        self.assertTrue(v["rules"]["R3"]["pass"])
        self.assertTrue(v["rules"]["R4"]["pass"])
        self.assertTrue(v["rules"]["R1"]["pass"])


class TestS23OasisCoffee(unittest.TestCase):
    def test_anchorless_date_needs_review(self):
        # 30/10/69 with a 2-digit year and no BE/CE anchor: the honest
        # gold leaves issue_date null and both date rules fire soft.
        doc = fresh_seed("S23")
        self.assertIsNone(doc["dates"]["issue_date"])
        era = doc["dates"]["era_resolution"]
        self.assertEqual(era["detected_era"], "ambiguous")
        self.assertIsNone(era["anchor_used"])
        v = validate(doc)
        self.assertFalse(v["rules"]["R7"]["pass"])
        self.assertIn("anchor", v["rules"]["R7"]["detail"])
        self.assertFalse(v["rules"]["R13"]["pass"])
        self.assertEqual(v["hard_failed"], [])
        self.assertEqual(triage(doc, v)["decision"], "needs_review")

    def test_no_tax_id_unclaimable(self):
        # No 13-digit ID anywhere: absent passes R6, but the unknown
        # form keeps the VAT claim unproven via R14.
        doc = fresh_seed("S23")
        self.assertIsNone(doc["issuer"]["tax_id"])
        self.assertEqual(doc["form"], "unknown")
        self.assertFalse(doc["can_claim_input_vat"])
        v = validate(doc)
        self.assertTrue(v["rules"]["R6"]["pass"])
        self.assertFalse(v["rules"]["R14"]["pass"])

    def test_printed_gross_recomputed(self):
        # The printed "VATABLE 120.00" is the gross, not the base:
        # 12000 - round(12000*7/107) = 11215 keeps R3/R4 green.
        doc = fresh_seed("S23")
        self.assertEqual(doc["totals"]["vat_amount"], 785)
        self.assertEqual(doc["totals"]["vatable_amount"], 11215)
        v = validate(doc)
        self.assertTrue(v["rules"]["R3"]["pass"])
        self.assertTrue(v["rules"]["R4"]["pass"])
        # Regression pin: trusting the printed 12000 must fail R4.
        doc["totals"]["vatable_amount"] = 12000
        self.assertFalse(validate(doc)["rules"]["R4"]["pass"])

    def test_traps_discarded_single_line(self):
        doc = fresh_seed("S23")
        self.assertEqual(
            doc["document_number"], "1RC102569/008592")
        lines = doc["line_items"]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["description"], "Mango Smoothie")
        # ITEMS count row, wifi password and expiry date are traps.
        self.assertIn("scjraa63", doc["discarded_text"])
        self.assertIn("31/10/69", doc["discarded_text"])


class TestS7CpAxtraSecondBranch(unittest.TestCase):
    def test_ddmmyyyy_by_vendor_convention(self):
        # Raw 05/09/2026 is day/month-ambiguous in isolation, but S2 is
        # the same retailer and POS family with a day-27 date, which
        # proves DD/MM/YYYY ordering: this is 5 Sept 2026.
        doc = fresh_seed("S7")
        self.assertEqual(doc["dates"]["raw_date_string"],
                         "05/09/2026 13:28")
        self.assertEqual(doc["dates"]["issue_date"], "2026-09-05")
        v = validate(doc)
        self.assertTrue(v["rules"]["R7"]["pass"])

    def test_masked_rid_is_not_a_pos_stamp(self):
        # A masked RID (XXXX...01) must not become a POS identifier.
        doc = fresh_seed("S7")
        self.assertIsNone(doc["pos_identifier"])
        mask = doc["discarded_text"][0]
        self.assertTrue(mask.startswith("X") and mask.endswith("01"))
        self.assertIsNone(normalise_pos_identifier(f"RID. {mask}"))

    def test_unlabeled_stamps_not_assembled(self):
        # 6662 001 66623002 5619 carry no labels: no doc number, same
        # as S2's 1681 002 16811002 3499 line.
        doc = fresh_seed("S7")
        self.assertIsNone(doc["document_number"])
        self.assertIn("6662 001 66623002 5619", doc["discarded_text"])

    def test_card_payment_with_psp_ref(self):
        pay = fresh_seed("S7")["payments"]
        self.assertEqual(len(pay), 1)
        self.assertEqual(pay[0]["amount"], 6900)
        self.assertEqual(pay[0]["method_raw"], "On-line card")
        self.assertEqual(pay[0]["external_ref"], "61399177Q8HQ100000")
        v = validate(fresh_seed("S7"))
        self.assertTrue(v["rules"]["R5"]["pass"])

    def test_coin_rows_are_traps(self):
        # Earned 0.20 and prior-balance 10.73 coins must not leak into
        # totals or payments: single line, single tender, 6900 total.
        doc = fresh_seed("S7")
        self.assertIn("0.20", doc["discarded_text"])
        self.assertIn("10.73", doc["discarded_text"])
        self.assertEqual(doc["totals"]["grand_total"], 6900)
        v = validate(doc)
        self.assertEqual(failed_rules(v), [])
        self.assertEqual(triage(doc, v)["decision"], "auto_accept")


class TestS8JayToSeafood(unittest.TestCase):
    def test_print_time_issues_two_timestamp_bill(self):
        # Check-in 18:53 and print 18:57 share the date; the print
        # time issues the bill, the check-in is discarded.
        doc = fresh_seed("S8")
        self.assertEqual(doc["dates"]["raw_date_string"],
                         "05-09-2569 18:57")
        self.assertEqual(doc["dates"]["issue_date"], "2026-09-05")
        self.assertEqual(doc["dates"]["era_resolution"]["detected_era"],
                         "BE")
        self.assertIn("05-09-2569 18:53", doc["discarded_text"])
        v = validate(doc)
        self.assertTrue(v["rules"]["R7"]["pass"])

    def test_master_typo_kept_verbatim(self):
        # The POS master prints น้ำโศก (for น้ำโค้ก): gold matches the
        # slip, never the corrected spelling.
        lines = fresh_seed("S8")["line_items"]
        self.assertEqual(lines[2]["description"], "น้ำโศก(เล็ก)")
        self.assertEqual(lines[2]["description_raw"], "น้ำโศก(เล็ก)")
        self.assertEqual(lines[1]["description"],
                         "(คะน้า,แขนง)หมูกรอบราดข้าว")

    def test_count_and_zone_are_not_lines(self):
        # ยอดรวม count 3 and zone นอก-3 stay out of the 3 lines,
        # which sum exactly to the 240.00 total.
        doc = fresh_seed("S8")
        self.assertEqual(len(doc["line_items"]), 3)
        self.assertIn("3", doc["discarded_text"])
        self.assertIn("นอก - 3", doc["discarded_text"])
        v = validate(doc)
        self.assertTrue(v["rules"]["R1"]["pass"])

    def test_unpaid_unknown_form_needs_review(self):
        # No tender rows, no tax ID, no ABB/full marks: R14 alone and
        # soft, like S21.
        doc = fresh_seed("S8")
        self.assertEqual(doc["payments"], [])
        self.assertEqual(doc["status"], "unpaid")
        self.assertIsNone(doc["issuer"]["tax_id"])
        v = validate(doc)
        self.assertEqual(failed_rules(v), ["R14"])
        self.assertEqual(v["hard_failed"], [])
        self.assertEqual(triage(doc, v)["decision"], "needs_review")


class TestS9DairyQueen(unittest.TestCase):
    def test_mmdd_by_pos_locale(self):
        # 09/06/2026 is month-ambiguous in isolation, but the 12-hour
        # "3:32 PM" clock and Host/Check Closed vocabulary prove a US
        # POS locale, which prints MM/DD: June 9, not Sept 6.
        doc = fresh_seed("S9")
        self.assertEqual(doc["dates"]["raw_date_string"],
                         "09/06/2026 3:32 PM")
        self.assertEqual(doc["dates"]["issue_date"], "2026-06-09")
        v = validate(doc)
        self.assertTrue(v["rules"]["R7"]["pass"])

    def test_priced_modifier_attaches(self):
        # +KITKAT is a priced modifier of line 1: R8 needs the parent
        # link, R1 still sums it into the 99.00 subtotal.
        lines = fresh_seed("S9")["line_items"]
        self.assertEqual(lines[1]["description"], "+KITKAT")
        self.assertTrue(lines[1]["is_modifier"])
        self.assertEqual(lines[1]["parent_line_number"], 1)
        v = validate(fresh_seed("S9"))
        self.assertTrue(v["rules"]["R1"]["pass"])
        self.assertTrue(v["rules"]["R8"]["pass"])

    def test_spaced_pos_stamp_joins(self):
        # "E 05 20100 02 A3693" joins to the E+14 family shape.
        pos = fresh_seed("S9")["pos_identifier"]
        self.assertEqual(pos, "E052010002A3693")
        self.assertEqual(len(pos), 15)

    def test_labelled_number_beats_queue_stamps(self):
        # TAX INVOICE (ABB): 11390 is the doc number; Q#3 and 10174
        # are queue/check stamps, survey figures are traps.
        doc = fresh_seed("S9")
        self.assertEqual(doc["document_number"], "11390")
        self.assertIn("Q#3", doc["discarded_text"])
        self.assertIn("10174", doc["discarded_text"])
        self.assertIn("*จากเค้กราคาปกติ 499 และ 429 เท่านั้น*",
                      doc["discarded_text"])
        v = validate(doc)
        self.assertEqual(failed_rules(v), [])
        self.assertEqual(triage(doc, v)["decision"], "auto_accept")


if __name__ == "__main__":
    unittest.main()
