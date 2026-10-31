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
            self.assertEqual(report["overall"]["n"], 22)
            self.assertEqual(report["overall"]["doc_all_correct"], 22)
            # S2, S7-S9, S11 and S15-S17 have no VAT line:
            # totals.vat_amount scores over 14 docs.
            overall = report["overall"]
            self.assertEqual(overall["per_field_n"]["totals.vat_amount"], 14)
            self.assertEqual(overall["per_field_counts"]["totals.vat_amount"], 14)
            self.assertEqual(overall["per_field_n"]["totals.grand_total"],
                             22)
            self.assertEqual(report["missing_preds"], [])
            self.assertEqual(report["faded"]["n"], 1)
            self.assertEqual(report["faded"]["doc_all_correct"], 1)
            # A degraded pred must show up in per-field counts.
            preds["S2"]["totals"]["grand_total"] = 1
            with open(preds_p, "w", encoding="utf-8") as f:
                json.dump(preds, f)
            report = run_eval(preds_p, labels_d, faded_p)
            self.assertEqual(report["overall"]["doc_all_correct"], 21)
            counts = report["overall"]["per_field_counts"]
            self.assertEqual(counts["totals.grand_total"], 21)


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


class TestS10Tsuruha(unittest.TestCase):
    def test_negative_promo_rows_are_lines(self):
        # The B1G1 pair and the Biore promo print as rows with
        # negative amounts: they sum into R1 as lines, not as
        # discount_total (which stays 0: no such row is printed).
        doc = fresh_seed("S10")
        lines = doc["line_items"]
        self.assertEqual(len(lines), 6)
        self.assertEqual(
            [li["line_total"] for li in lines],
            [12500, -6250, 12500, -6250, 29900, -6000])
        self.assertEqual(doc["totals"]["discount_total"], 0)
        v = validate(doc)
        self.assertTrue(v["rules"]["R1"]["pass"])

    def test_printed_vat_split_exact(self):
        # First seed with printed Vatable/VAT rows: 340.19 + 23.81 =
        # 364.00 and the VAT exactly matches round(36400*7/107).
        doc = fresh_seed("S10")
        self.assertEqual(doc["totals"]["vatable_amount"], 34019)
        self.assertEqual(doc["totals"]["vat_amount"], 2381)
        self.assertEqual(doc["totals"]["vat_amount_computed"], 2381)
        v = validate(doc)
        self.assertTrue(v["rules"]["R3"]["pass"])
        self.assertTrue(v["rules"]["R4"]["pass"])

    def test_ddmm_by_clock_and_no_stamp(self):
        # 24-hour 16:10 clock means Thai-locale DD/MM (unlike S9's
        # 12-hour US clock), corroborated by 2609 inside the NO stamp.
        doc = fresh_seed("S10")
        self.assertEqual(doc["dates"]["issue_date"], "2026-09-06")
        self.assertIn("2609", doc["document_number"])
        v = validate(doc)
        self.assertTrue(v["rules"]["R7"]["pass"])

    def test_traps_discarded_pii_omitted(self):
        # Count row, points figures, relative periods are traps; the
        # member and salesperson names stay out of the fixture (PII).
        doc = fresh_seed("S10")
        self.assertIn("Total 3.00 Items", doc["discarded_text"])
        self.assertIn("0 18 72 -", doc["discarded_text"])
        self.assertIn("***รับคืนหรือเปลี่ยนสินค้าภายใน 7 วัน***",
                      doc["discarded_text"])
        blob = json.dumps(doc, ensure_ascii=False)
        self.assertNotIn("ไกรสร", blob)
        self.assertNotIn("วิรดา", blob)
        v = validate(doc)
        self.assertEqual(failed_rules(v), [])
        self.assertEqual(triage(doc, v)["decision"], "auto_accept")


class TestS11PaBoonCafe(unittest.TestCase):
    def test_total_subtotal_grand_chain(self):
        # The totals.total resolution, pinned on real rows: total is
        # the gross line sum, subtotal the net before service, grand
        # the final. R1 and R2 pass on the resolved chain.
        doc = fresh_seed("S11")
        t = doc["totals"]
        self.assertEqual(t["total"], 53500)
        self.assertEqual(t["discount_total"], 4950)
        self.assertEqual(t["rounding_adjustment"], 50)
        self.assertEqual(t["subtotal"], 48600)
        self.assertEqual(t["grand_total"], 48600)
        v = validate(doc)
        self.assertTrue(v["rules"]["R1"]["pass"])
        self.assertTrue(v["rules"]["R2"]["pass"])

    def test_discount_base_is_food_only(self):
        # 49.50 is 10% of the FOOD 495.00, not of the 535.00 total:
        # misreading the base breaks the chain by 4.00.
        doc = fresh_seed("S11")
        food = doc["line_items"][0]["line_total"]
        self.assertEqual(food, 49500)
        self.assertEqual(doc["totals"]["discount_total"], food // 10)
        self.assertNotEqual(doc["totals"]["discount_total"],
                            doc["totals"]["total"] // 10)

    def test_category_headers_flagged_not_summed(self):
        # อาหาร/เครื่องดื่ม headers precede their items and carry no
        # quantity; flagged, R1 excludes them from the charge sum.
        doc = fresh_seed("S11")
        cats = [li for li in doc["line_items"]
                if li.get("is_category_subtotal")]
        self.assertEqual(len(cats), 2)
        for cat in cats:
            self.assertNotIn("quantity", cat)
        self.assertEqual(sum(li["line_total"] for li in
                             doc["line_items"] if not li.get(
                                 "is_category_subtotal")), 53500)
        v = validate(doc)
        self.assertTrue(v["rules"]["R9"]["pass"])

    def test_short_branch_code_and_form_need_review(self):
        # Branch "3" is genuinely printed but trips R11's 4-5 digit
        # convention; with R14 both fire soft, like S3's R11.
        doc = fresh_seed("S11")
        self.assertEqual(doc["issuer"]["branch_code"], "3")
        self.assertEqual(doc["status"], "unpaid")
        self.assertIsNone(doc["document_number"])
        v = validate(doc)
        self.assertEqual(failed_rules(v), ["R11", "R14"])
        self.assertEqual(v["hard_failed"], [])
        self.assertEqual(triage(doc, v)["decision"], "needs_review")
        blob = json.dumps(doc, ensure_ascii=False)
        self.assertNotIn("2066268766275002", blob)
        self.assertNotIn("ไกรสร", blob)


class TestS12StarbucksMisprint(unittest.TestCase):
    def test_one_digit_misprint_hard_blocks_r6(self):
        # ...6688 vs S4's ...8688: a single printed digit breaks the
        # checksum, and R6 must hard-fail true gold (first blocked
        # seed) while S4's ID keeps passing.
        bad = fresh_seed("S12")["issuer"]["tax_id"]
        good = fresh_seed("S4")["issuer"]["tax_id"]
        self.assertEqual(
            sum(a != b for a, b in zip(bad, good)), 1)
        v = validate(fresh_seed("S12"))
        self.assertFalse(v["rules"]["R6"]["pass"])
        self.assertEqual(v["hard_failed"], ["R6"])
        self.assertTrue(validate(fresh_seed("S4"))["rules"]["R6"]["pass"])

    def test_ambiguous_date_mirrors_s4(self):
        # "Sep09 26" carries the same unresolvable 2-digit year as
        # S4's "Aug28 26": null issue, ambiguous era, R7+R13 fail.
        doc = fresh_seed("S12")
        self.assertIsNone(doc["dates"]["issue_date"])
        self.assertEqual(doc["dates"]["era_resolution"]["detected_era"],
                         "ambiguous")
        v = validate(doc)
        self.assertFalse(v["rules"]["R7"]["pass"])
        self.assertFalse(v["rules"]["R13"]["pass"])
        self.assertEqual(failed_rules(v), ["R13", "R6", "R7"])
        t = triage(doc, v)
        self.assertEqual(t["decision"], "needs_review")
        self.assertIn("R6", t["reason"])

    def test_amount_first_vat_and_abb_number(self):
        # "1.64 VAT TTL" prints the VAT amount first with a 25.00
        # total echo beside it; the ABB invoice number (not Chk) is
        # the document number, as on S4.
        doc = fresh_seed("S12")
        self.assertEqual(doc["totals"]["vat_amount"], 164)
        self.assertEqual(doc["totals"]["vatable_amount"], 2336)
        self.assertEqual(doc["document_number"], "260909-01-08576")
        self.assertIn("Chk 0100339186", doc["discarded_text"])
        v = validate(doc)
        self.assertTrue(v["rules"]["R3"]["pass"])
        self.assertTrue(v["rules"]["R4"]["pass"])

    def test_loyalty_traps_and_pii_omitted(self):
        doc = fresh_seed("S12")
        for trap in ("Card Balance is 1800.00 THB", "21Aug27",
                     "13Sep26", "31Dec26", "OTKIOHSLFT"):
            self.assertIn(trap, doc["discarded_text"])
        blob = json.dumps(doc, ensure_ascii=False)
        self.assertNotIn("Kraisorn", blob)


class TestS13Watsons(unittest.TestCase):
    def test_per_line_rounding_within_tolerance(self):
        # POS rounds VAT per line (164 x 2 = 328), the pipeline on
        # the grand (327): R3's +-1 absorbs exactly this policy gap.
        doc = fresh_seed("S13")
        self.assertEqual(doc["totals"]["vat_amount"], 328)
        self.assertEqual(doc["totals"]["vat_amount_computed"], 327)
        self.assertEqual(doc["totals"]["vatable_amount"], 4672)
        v = validate(doc)
        self.assertTrue(v["rules"]["R3"]["pass"])
        self.assertTrue(v["rules"]["R4"]["pass"])

    def test_sku_strips_t_flag_unknown(self):
        # Leading SKU codes live in description_raw, not the name;
        # the T taxable flag is outside the V/N/E vocabulary.
        lines = fresh_seed("S13")["line_items"]
        self.assertEqual(lines[0]["description"], "#HDBRPMNightRepa@")
        self.assertEqual(lines[0]["description_raw"],
                         "311773 #HDBRPMNightRepa@")
        self.assertEqual(lines[1]["description"], "#HadabireiPr@")
        for li in lines:
            self.assertEqual(li["vat_flag"], "unknown")

    def test_receipt_number_decomposes(self):
        # #604002090920260005 = store 604 + terminal 002 + date
        # 09092026 + seq 0005, fixing branch_code "00604".
        doc = fresh_seed("S13")
        num = doc["document_number"]
        self.assertEqual(num, "604002090920260005")
        self.assertTrue(num.startswith("604002"))
        self.assertIn("09092026", num)
        self.assertTrue(num.endswith("0005"))
        self.assertEqual(doc["issuer"]["branch_code"], "00604")
        v = validate(doc)
        self.assertEqual(failed_rules(v), [])
        self.assertEqual(triage(doc, v)["decision"], "auto_accept")

    def test_traps_and_call_center_not_phone(self):
        # Count, change, eStamp/loyalty figures, terminal refs and
        # the barcode are traps; the call-center Tel is not the
        # issuer phone, and the cashier name stays out (PII).
        doc = fresh_seed("S13")
        for trap in ("2", "CHANGE 0.00",
                     "Opening eStamp Balance 10",
                     "Loyalty acc.number 9930840801***",
                     "Tel: 02-0178899", "TID# 73906252",
                     "TRACE# 138340", "870604021403220260909"):
            self.assertIn(trap, doc["discarded_text"])
        self.assertNotIn("phone", doc["issuer"])
        blob = json.dumps(doc, ensure_ascii=False)
        self.assertNotIn("Kuhaiiii", blob)


class TestS14JonesDelivery(unittest.TestCase):
    def test_header_modifier_and_charges(self):
        # ** delivery section header (0) plus a 0.00 side-note
        # modifier on the steak; charges are 110 + 139 = 249.
        lines = fresh_seed("S14")["line_items"]
        self.assertTrue(lines[0]["is_section_header"])
        self.assertEqual(lines[0]["line_total"], 0)
        self.assertTrue(lines[2]["is_modifier"])
        self.assertEqual(lines[2]["parent_line_number"], 2)
        self.assertEqual(lines[2]["line_total"], 0)
        v = validate(fresh_seed("S14"))
        self.assertTrue(v["rules"]["R1"]["pass"])
        self.assertTrue(v["rules"]["R8"]["pass"])

    def test_inline_promo_math_is_trap(self):
        # 249.- is the set-total echo and (219-109)[49.8%] the
        # steak's promo annotation: neither is a charge line, and
        # the steak books at its 110.00 net.
        doc = fresh_seed("S14")
        self.assertEqual(doc["line_items"][1]["line_total"], 11000)
        self.assertIn("249.- (219.00-109.00)[49.8%]",
                      doc["discarded_text"])
        self.assertIn("* SP สเต็กสะโพกไก่ขี้โมโห คู่ แรปทูน่าอ้วน",
                      doc["discarded_text"])

    def test_symmetric_date_and_printed_split(self):
        # 09/09 reads the same under DD/MM and MM/DD; the printed
        # Taxable/Tax split matches the recomputation exactly.
        doc = fresh_seed("S14")
        self.assertEqual(doc["dates"]["issue_date"], "2026-09-09")
        self.assertEqual(doc["dates"]["printed_at"],
                         "2026-09-09T14:19:00")
        self.assertEqual(doc["totals"]["vatable_amount"], 23271)
        self.assertEqual(doc["totals"]["vat_amount"], 1629)
        v = validate(doc)
        self.assertTrue(v["rules"]["R3"]["pass"])
        self.assertTrue(v["rules"]["R4"]["pass"])
        self.assertTrue(v["rules"]["R5"]["pass"])

    def test_channel_traps_and_pii_omitted(self):
        doc = fresh_seed("S14")
        self.assertEqual(doc["document_number"], "JS001/ESP017940")
        for trap in ("Order No: 15142", "Ref No: 689",
                     "Table No: 02", "Cutlery: No",
                     "** 09/09/2026 14:19 **",
                     "Scan here to share your feedback!",
                     "@Jonessalad"):
            self.assertIn(trap, doc["discarded_text"])
        blob = json.dumps(doc, ensure_ascii=False)
        self.assertNotIn("Nantacha", blob)
        v = validate(doc)
        self.assertEqual(failed_rules(v), [])
        self.assertEqual(triage(doc, v)["decision"], "auto_accept")


class TestS15Tops(unittest.TestCase):
    def test_promo_line_and_verbatim_oddity(self):
        # -3.00 Mix&Match is a charge line (S10 pattern), not
        # discount_total; the odd first-line name stays verbatim.
        doc = fresh_seed("S15")
        self.assertEqual(
            [li["line_total"] for li in doc["line_items"]],
            [800, 1600, -300, 1600])
        self.assertEqual(doc["line_items"][0]["description"],
                         "โผล่น้ำแข็งกั่ว")
        self.assertEqual(doc["totals"]["discount_total"], 0)
        v = validate(doc)
        self.assertTrue(v["rules"]["R1"]["pass"])
        self.assertTrue(v["rules"]["R5"]["pass"])

    def test_digit_runs_route_to_review(self):
        # NP/STID/barcode digit runs look card-shaped to R11's
        # conservative scan: soft flag, human clears, like S3.
        doc = fresh_seed("S15")
        self.assertIn("NP_3724765260701", doc["discarded_text"])
        v = validate(doc)
        self.assertEqual(failed_rules(v), ["R11"])
        self.assertEqual(v["hard_failed"], [])
        self.assertIn("card", v["rules"]["R11"]["detail"])
        self.assertEqual(triage(doc, v)["decision"], "needs_review")

    def test_coupon_section_is_all_traps(self):
        # The coupon's code, % figures and three extra dates must
        # not move the receipt's date, discount or totals.
        doc = fresh_seed("S15")
        self.assertEqual(doc["dates"]["issue_date"], "2026-09-09")
        for trap in ("JOYNOW15", "30/08/69", "15.07.2026",
                     "30.09.2026"):
            self.assertIn(trap, doc["discarded_text"])
        self.assertEqual(doc["totals"]["discount_total"], 0)

    def test_receipt_number_and_pii_omitted(self):
        doc = fresh_seed("S15")
        self.assertEqual(doc["document_number"], "003 - 022725")
        self.assertIn("TP 003 - 023471", doc["discarded_text"])
        self.assertEqual(doc["issuer"]["phone"], "02-660-9092-3")
        self.assertIn("โทร 1467", doc["discarded_text"])
        blob = json.dumps(doc, ensure_ascii=False)
        self.assertNotIn("2471459066", blob)
        self.assertNotIn("ไกรสร", blob)
        self.assertNotIn("Natthaphat", blob)


class TestS16SevenSecondSlip(unittest.TestCase):
    def test_receipt_level_discount_not_line(self):
        # The 4.00 Coke/Sprite row sits after ยอดรวม printed
        # positive: S11-pattern discount_total, not a third line.
        doc = fresh_seed("S16")
        self.assertEqual(len(doc["line_items"]), 2)
        t = doc["totals"]
        self.assertEqual(t["total"], 8100)
        self.assertEqual(t["discount_total"], 400)
        self.assertEqual(t["subtotal"], 7700)
        v = validate(doc)
        self.assertTrue(v["rules"]["R1"]["pass"])
        self.assertTrue(v["rules"]["R2"]["pass"])

    def test_sister_slip_links_and_anchor(self):
        # Same store, entity and POS terminal as S22; BE date
        # resolves via the TID stamp like S22's.
        doc = fresh_seed("S16")
        s22 = fresh_seed("S22")
        for key in ("tax_id", "branch_code"):
            self.assertEqual(doc["issuer"][key], s22["issuer"][key])
        self.assertEqual(doc["pos_identifier"], s22["pos_identifier"])
        self.assertEqual(doc["dates"]["issue_date"], "2026-09-10")
        self.assertEqual(doc["dates"]["era_resolution"]["anchor_used"],
                         "TID#20260910000000005221682503")
        v = validate(doc)
        self.assertTrue(v["rules"]["R7"]["pass"])
        self.assertEqual(failed_rules(v), [])
        self.assertEqual(triage(doc, v)["decision"], "auto_accept")

    def test_stamp_traps_and_pii_omitted(self):
        doc = fresh_seed("S16")
        for trap in ("02314", "M-Stamp(บาท)", "3 ชิ้น",
                     "บิลนี้ประหยัด 4.00",
                     "** PayAtAll by Counter Service **",
                     "+42", "9143", "151269", "0-2826-7777"):
            self.assertIn(trap, doc["discarded_text"])
        self.assertNotIn("ไกรสร",
                         json.dumps(doc, ensure_ascii=False))


class TestS17ZaabOle(unittest.TestCase):
    def test_invoice_type_and_staff_row_branch(self):
        # First invoice-typed seed; the branch hides in the Staff
        # row. Unknown form with no tax ID: R14 alone, soft.
        doc = fresh_seed("S17")
        self.assertEqual(doc["document_type"], "invoice")
        self.assertEqual(doc["issuer"]["branch_name"], "ห้วยขวาง")
        self.assertEqual(doc["issuer"]["legal_name"],
                         "แซ่บโอเล่ by เชฟแม่ยงตำซ่า")
        v = validate(doc)
        self.assertEqual(failed_rules(v), ["R14"])
        self.assertEqual(v["hard_failed"], [])
        self.assertEqual(triage(doc, v)["decision"], "needs_review")

    def test_faded_dishes_verbatim(self):
        # Contrast-boosted zooms resolve the faded dish names; the
        # four lines sum exactly to the 185.00 subtotal.
        lines = fresh_seed("S17")["line_items"]
        self.assertEqual(
            [li["description"] for li in lines],
            ["นมหมูย่าง", "ลาบเป็ด", "ข้าวเหนียว",
             "โค้ก(ขวดเล็ก)375ML"])
        v = validate(fresh_seed("S17"))
        self.assertTrue(v["rules"]["R1"]["pass"])

    def test_counter_rows_are_traps(self):
        doc = fresh_seed("S17")
        for trap in ("Table: 2 นอก", "Guests: 1", "Items: 4"):
            self.assertIn(trap, doc["discarded_text"])
        self.assertEqual(doc["dates"]["issue_date"], "2026-09-10")
        self.assertEqual(doc["status"], "unpaid")
        v = validate(doc)
        self.assertTrue(v["rules"]["R5"]["pass"])

    def test_faded_split_lists_s17(self):
        # Second faded-thermal member after S5 for the eval split.
        faded = os.path.join(os.path.dirname(__file__), "..", "data",
                             "faded.txt")
        with open(faded, encoding="utf-8") as f:
            ids = [line.strip() for line in f if line.strip()]
        self.assertIn("S17", ids)


class TestS18PungSiam(unittest.TestCase):
    def test_abb_banktransfer_auto_accepts(self):
        # Clean bakery ABB: valid tax ID, exact math, explicit
        # BankTransfer tender row. Nothing fails: auto_accept.
        doc = fresh_seed("S18")
        self.assertEqual(doc["form"], "abbreviated")
        self.assertEqual(doc["document_number"], "RC6909130088")
        self.assertEqual(doc["pos_identifier"], "E041310002A3489")
        self.assertEqual(doc["payments"],
                         [{"amount": 6900, "method": "bank_transfer",
                           "method_raw": "BankTransfer:"}])
        v = validate(doc)
        self.assertEqual(v["hard_failed"], [])
        self.assertEqual(
            sorted(r for r, rp in v["rules"].items()
                   if not rp["pass"]), [])
        self.assertEqual(triage(doc, v)["decision"], "auto_accept")

    def test_printed_vat_pins_formula_third_time(self):
        # 4.51 = round(6900*7/107): third printed-VAT pin after
        # S13/S23, and 64.49 + 4.51 reconciles to 69.00 exactly.
        doc = fresh_seed("S18")
        self.assertEqual(doc["totals"]["vat_amount"], 451)
        self.assertEqual(doc["totals"]["vat_amount_computed"], 451)
        self.assertEqual(round(6900 * 7 / 107), 451)
        self.assertEqual(doc["totals"]["vatable_amount"], 6449)
        v = validate(doc)
        self.assertTrue(v["rules"]["R1"]["pass"])

    def test_traps_and_thai_digit_logo_year(self):
        # The ลูกค้าทั่วไป เงินสด line is a customer-type label,
        # not the tender; the logo year is Thai digits ๒๕๑๕ (=2515,
        # duplicating the Arabic-digit company line used verbatim).
        doc = fresh_seed("S18")
        for trap in ("S/N# E720M01014", "เปิดโต๊ะ: 13:04",
                     "พิมพ์ใบเรียกเก็บเงิน: 13:04",
                     "ลูกค้าทั่วไป เงินสด", "เงินทอน: 0.00",
                     "หมายเหตุ:", "ราคารวมภาษีมูลค่าเพิ่มแล้ว",
                     "Version (3.0.2502.1)"):
            self.assertIn(trap, doc["discarded_text"])
        self.assertEqual(doc["issuer"]["legal_name"],
                         "บริษัท ปังสยาม พ.ศ.2515 จำกัด")
        self.assertEqual(doc["issuer"]["branch_code"], "00012")
        self.assertEqual(doc["line_items"][0]["description"],
                         "สเลอปี้ทูโทน")
        self.assertEqual(doc["dates"]["issue_date"], "2026-09-13")


class TestS19WatsonsRatchada(unittest.TestCase):
    def test_sister_slip_matches_s13_and_auto_accepts(self):
        # Same two products and 50.00 as S13; the 328-vs-327
        # per-line-rounding gap is absorbed by R3's +-1 again.
        doc = fresh_seed("S19")
        self.assertEqual(doc["form"], "abbreviated")
        self.assertEqual(doc["issuer"]["tax_id"], "0105539086260")
        self.assertEqual(
            [li["description"] for li in doc["line_items"]],
            ["#HDBRPMNightRepa@", "#HadabireiPr@"])
        self.assertEqual(doc["totals"]["vat_amount"], 328)
        self.assertEqual(doc["totals"]["vat_amount_computed"], 327)
        self.assertEqual(doc["payments"][0]["method"], "qr_promptpay")
        self.assertEqual(doc["payments"][0]["external_ref"],
                         "EDC1791002675378943")
        v = validate(doc)
        self.assertEqual(failed_rules(v), [])
        self.assertEqual(triage(doc, v)["decision"], "auto_accept")

    def test_encoded_date_is_stale_trap(self):
        # #634002100320260007 = store 634 + terminal 002 + date
        # 10032026 + seq 0007, but the header prints 30OCT2026:
        # the encoded 1003 is stale, the printed date wins, and
        # the barcode (same stale tail) is discarded verbatim.
        doc = fresh_seed("S19")
        num = doc["document_number"]
        self.assertEqual(num, "634002100320260007")
        self.assertTrue(num.startswith("634002"))
        self.assertIn("10032026", num)
        self.assertTrue(num.endswith("0007"))
        self.assertEqual(doc["issuer"]["branch_code"], "00634")
        self.assertEqual(doc["dates"]["issue_date"], "2026-10-30")
        self.assertEqual(doc["dates"]["raw_date_string"],
                         "30OCT2026 11:44:46")
        self.assertIn("3706340211441120261003",
                      doc["discarded_text"])

    def test_traps_and_no_machine_id(self):
        # POS(02)# is a terminal label, not an E machine ID;
        # 02-0178899 is the call center (no phone key, S13
        # precedent); cashier name omitted as PII.
        doc = fresh_seed("S19")
        self.assertIsNone(doc["pos_identifier"])
        self.assertNotIn("phone", doc["issuer"])
        for trap in ("POS(02)#", "2", "CHANGE 0.00",
                     "Loyalty acc.number 9930840807***",
                     "Opening Balance 30", "Earned value 2",
                     "Closing balance 32", "Tel: 02-0178899",
                     "ISSUER# PROMPTPAY", "TID# 73906592",
                     "TRACE# 103125", "R 002", "C00C5", "#0007"):
            self.assertIn(trap, doc["discarded_text"])
        blob = json.dumps(doc, ensure_ascii=False)
        self.assertNotIn("Nanthita", blob)
        # SKU2 differs from S13's 309086: the 4th glyph reads C.
        self.assertEqual(doc["line_items"][1]["description_raw"],
                         "309C76 #HadabireiPr@")


if __name__ == "__main__":
    unittest.main()
