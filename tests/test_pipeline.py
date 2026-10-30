import argparse
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from ptl.api.cli import cmd_export
from ptl.pipeline.extract import (EXTRACTION_PROMPT_RULES,
                                  build_document,
                                  normalise_pos_identifier,
                                  split_embedded_qty, strip_vat_flag)
from ptl.pipeline.ingest import content_hash, mask_pii
from ptl.pipeline.quality import quality_gate
from ptl.pipeline.validate_rules import r1_line_sum, r4_vat_split
from ptl.pipeline.export import COLUMNS, to_csv, to_row
from tests.fixtures import fresh

# Minimum ledger columns, hand-transcribed from 05 section 5. `note`
# rides after them as a platform extension.
SPEC_MINIMUM_COLUMNS = ["date", "document_number", "document_type",
                        "form", "can_claim_input_vat",
                        "seller_legal_name", "seller_tax_id",
                        "branch_code", "vatable", "vat", "non_vatable",
                        "grand_total", "payment_method", "review_status",
                        "source_image_ref"]


class TestPipelineBits(unittest.TestCase):
    def test_vat_suffix(self):
        self.assertEqual(strip_vat_flag("Noodles V"), ("Noodles", "V"))
        self.assertEqual(strip_vat_flag("Plain"), ("Plain", "unknown"))

    def test_embedded_qty(self):
        self.assertEqual(split_embedded_qty("Drink X2"), ("Drink", 2.0))
        self.assertEqual(split_embedded_qty("Noodles"), ("Noodles", None))

    def test_pos(self):
        self.assertEqual(normalise_pos_identifier("POS E123456789012 ok"),
                         "E123456789012")
        self.assertIsNone(normalise_pos_identifier("nope"))

    def test_pos_never_clips_longer_stamps(self):
        # 02 §9's own examples are E + 14 chars despite the "E + 12"
        # prose: the normaliser must return the full run, never clip.
        for label, stamp in [
                ("POS ID :", "E020100002A2158"),  # S1
                ("RID.", "E020100002A2259"),  # S2
                ("POS#", "E020110002A1570"),  # S4
                ("RD:", "E041210002A5885"),  # S6
                ("POS ID :", "E02010000202474")]:  # S22, all digits
            with self.subTest(stamp=stamp):
                self.assertEqual(
                    normalise_pos_identifier(f"{label} {stamp}"), stamp)

    def test_pos_rejects_mid_token_and_short(self):
        # Never start mid-token (XE... is not a stamp); short E-runs
        # like S3's ESP014867 survey code are not stamps either.
        self.assertIsNone(
            normalise_pos_identifier("XE020100002A2158"))
        self.assertIsNone(normalise_pos_identifier("JS001/ESP014867"))

    def test_prompt_pins_labelled_doc_numbers(self):
        # S2's '16811002 3499' was assembled from an unlabeled stamp and
        # S5's R# prefix was dropped: the prompt must pin both shut.
        # Live obedience is verified by re-extraction, not this pin.
        self.assertIn("attached prefixes", EXTRACTION_PROMPT_RULES)
        self.assertIn("never assemble one from store/terminal/sequence",
                      EXTRACTION_PROMPT_RULES)

    def test_prompt_pins_anchor_definition(self):
        # S4's invoice fragment 260828 must not resolve "Aug28 26", while
        # S5's full TID#20260828 stamp must keep resolving its date.
        # Live obedience is verified by re-extraction, not this pin.
        self.assertIn("YYMMDD fragment", EXTRACTION_PROMPT_RULES)
        self.assertIn("never resolves the year", EXTRACTION_PROMPT_RULES)

    def test_prompt_pins_branch_transcription(self):
        # S4's leading 14098 was omitted in three straight runs while the
        # same store number extracted fine on S12: pin the convention.
        # Live obedience is verified by re-extraction, not this pin.
        self.assertIn("transcribe it even when unlabeled",
                      EXTRACTION_PROMPT_RULES)

    def test_prompt_pins_tender_discount(self):
        # S1's AIS 10.00 is a tender split (35.00 QR + 10.00 AIS against a
        # 45.00 total), not a deduction: Spark emitted discount_total 1000
        # and R1 blocked the doc. Pin the distinction shut.
        # Live obedience is verified by re-extraction, not this pin.
        self.assertIn("tender, not discount_total", EXTRACTION_PROMPT_RULES)
        self.assertIn("subtotal - discount = total", EXTRACTION_PROMPT_RULES)

    def test_prompt_pins_branch_precedence(self):
        # S1 prints VAT branch 00031 with the issuer legal name and shop
        # code 2083 with the brand line: Spark flip-flopped between them.
        # Live obedience is verified by re-extraction, not this pin.
        self.assertIn("printed with the issuer legal name",
                      EXTRACTION_PROMPT_RULES)
        self.assertIn("not a shop or counter code",
                      EXTRACTION_PROMPT_RULES)

    def test_prompt_pins_form_no_guess(self):
        # S23 carries no ABB mark and no buyer block: Spark flip-flopped
        # abbreviated/unknown across runs, and an abbreviated guess would
        # suppress a deserved R14 review. Pin the no-guess convention.
        # Live obedience is verified by re-extraction, not this pin.
        self.assertIn("never default to abbreviated",
                      EXTRACTION_PROMPT_RULES)
        self.assertIn("explicit ABB mark", EXTRACTION_PROMPT_RULES)

    def test_prompt_pins_verbatim_descriptions(self):
        # S22 lines flip three ways across runs: stray H kept vs
        # stripped, and พาสฯ expanded to พาสเจอร์. The S5 precedent is
        # verbatim-minus-stray: pin it.
        # Live obedience is verified by re-extraction, not this pin.
        self.assertIn("never expand abbreviations",
                      EXTRACTION_PROMPT_RULES)
        self.assertIn("printer-stray", EXTRACTION_PROMPT_RULES)

    def test_prompt_pins_status_vocabulary(self):
        # S21 runs invented paid-ish statuses (extracted, ok) where the
        # seed says unpaid. Pin the vocabulary and the tender rule.
        # Live obedience is verified by re-extraction, not this pin.
        self.assertIn("never invent statuses", EXTRACTION_PROMPT_RULES)
        self.assertIn("paid only when payment/tender rows",
                      EXTRACTION_PROMPT_RULES)

    def test_pii_mask(self):
        self.assertNotIn("081-234-5678", mask_pii("call 081-234-5678"))
        self.assertNotIn("a@b.com", mask_pii("mail a@b.com"))

    def test_hash(self):
        self.assertEqual(len(content_hash(b"x")), 64)

    def test_gate(self):
        self.assertTrue(quality_gate(0.9, 0.8, 1.0).passed)
        self.assertFalse(quality_gate(0.01, 0.8, 1.0).passed)
        self.assertFalse(quality_gate(0.9, 0.8, 45.0).passed)

    def test_build_document_defaults(self):
        doc = build_document({"totals": {}})
        for key in ("discount_total", "rounding_adjustment", "service_charge",
                    "non_vatable_amount"):
            self.assertEqual(doc["totals"][key], 0)
        # Explicit values are never overwritten.
        doc = build_document({"totals": {"rounding_adjustment": -7}})
        self.assertEqual(doc["totals"]["rounding_adjustment"], -7)

    def test_build_infers_missing_subtotal_from_lines(self):
        # Glimmer omits subtotal rows it cannot transcribe (S6 prints
        # SubTotal/Total 32.00 yet emits neither key); R1's own equation
        # recovers the value deterministically.
        doc = build_document({"totals": {},
                              "line_items": [
                                  {"description": "A", "line_total": 2500},
                                  {"description": "B", "line_total": 5000}]})
        self.assertEqual(doc["totals"]["subtotal"], 7500)

    def test_build_subtotal_inference_honors_discount(self):
        doc = build_document({"totals": {"discount_total": 1000},
                              "line_items": [{"description": "A",
                                              "line_total": 4500}]})
        self.assertEqual(doc["totals"]["subtotal"], 3500)

    def test_build_never_overwrites_explicit_subtotal(self):
        # A disagreeing subtotal is R1's business, never build's to mask.
        doc = build_document({"totals": {"subtotal": 9999},
                              "line_items": [{"description": "A",
                                              "line_total": 4500}]})
        self.assertEqual(doc["totals"]["subtotal"], 9999)

    def test_build_subtotal_skipped_without_complete_lines(self):
        doc = build_document({"totals": {}})
        self.assertNotIn("subtotal", doc["totals"])
        doc = build_document({"totals": {},
                              "line_items": [{"description": "A"}]})
        self.assertNotIn("subtotal", doc["totals"])
        doc = build_document({"totals": {},
                              "line_items": [{"description": "H",
                                              "line_total": 100,
                                              "is_section_header": True}]})
        self.assertNotIn("subtotal", doc["totals"])

    def test_inferred_subtotal_always_passes_r1(self):
        # Inference uses R1's line set and equation: agreement holds by
        # construction, so the default can never trip the rule.
        doc = build_document({"totals": {"discount_total": 1000,
                                          "rounding_adjustment": 1},
                              "line_items": [
                                  {"description": "A", "line_total": 4500},
                                  {"description": "sub",
                                   "line_total": 4500,
                                   "is_category_subtotal": True}]})
        self.assertEqual(doc["totals"]["subtotal"], 3501)
        passed, _ = r1_line_sum(doc)
        self.assertTrue(passed)

    def test_build_infers_missing_vatable_from_grand(self):
        # Glimmer S1 emits grand+vat but no vatable; R4's own equation
        # recovers it deterministically (grand = vatable+vat+nonvat
        # holds in both inclusive and exclusive mode).
        doc = build_document({"totals": {"grand_total": 4500,
                                          "vat_amount": 294}})
        self.assertEqual(doc["totals"]["vatable_amount"], 4206)

    def test_build_vatable_inference_honors_nonvat(self):
        doc = build_document({"totals": {"grand_total": 4500,
                                          "vat_amount": 294,
                                          "non_vatable_amount": 500}})
        self.assertEqual(doc["totals"]["vatable_amount"], 3706)

    def test_build_never_overwrites_explicit_vatable(self):
        # A disagreeing vatable is R4's business, never build's to mask.
        doc = build_document({"totals": {"grand_total": 4500,
                                          "vat_amount": 294,
                                          "vatable_amount": 1}})
        self.assertEqual(doc["totals"]["vatable_amount"], 1)

    def test_build_vatable_skipped_without_grand_and_vat(self):
        doc = build_document({"totals": {"grand_total": 4500}})
        self.assertNotIn("vatable_amount", doc["totals"])
        doc = build_document({"totals": {"vat_amount": 294}})
        self.assertNotIn("vatable_amount", doc["totals"])
        doc = build_document({"totals": {}})
        self.assertNotIn("vatable_amount", doc["totals"])

    def test_inferred_vatable_always_passes_r4(self):
        doc = build_document({"totals": {"grand_total": 4500,
                                          "vat_amount": 294,
                                          "non_vatable_amount": 500}})
        self.assertEqual(doc["totals"]["vatable_amount"], 3706)
        passed, _ = r4_vat_split(doc)
        self.assertTrue(passed)

    def test_build_strips_embedded_qty(self):
        doc = build_document({"line_items": [
            {"line_number": 1, "description": "ดัชชี่ผลไม้รวม125ก.X4",
             "line_total": 4900}]})
        (line,) = doc["line_items"]
        self.assertEqual(line["description"], "ดัชชี่ผลไม้รวม125ก.")
        self.assertEqual(line["description_raw"], "ดัชชี่ผลไม้รวม125ก.X4")
        self.assertEqual(line["quantity"], 4)
        self.assertEqual(line["quantity_source"], "embedded_in_name")

    def test_build_keeps_model_quantity_and_source(self):
        # S2's live shape: model already split qty; only the name is dirty.
        doc = build_document({"line_items": [
            {"description": "Drink X2", "quantity": 2,
             "quantity_source": "embedded_in_name", "line_total": 100}]})
        (line,) = doc["line_items"]
        self.assertEqual(line["description"], "Drink")
        self.assertEqual(line["quantity"], 2)
        self.assertEqual(line["quantity_source"], "embedded_in_name")

    def test_build_qty_conflict_untouched(self):
        # A disagreeing quantity is a real signal: never mask it.
        doc = build_document({"line_items": [
            {"description": "Drink X2", "quantity": 3, "line_total": 100}]})
        (line,) = doc["line_items"]
        self.assertEqual(line["description"], "Drink X2")
        self.assertNotIn("description_raw", line)
        self.assertEqual(line["quantity"], 3)

    def test_build_plain_names_kept_quantity_assumed(self):
        doc = build_document({"line_items": [
            {"description": "Noodles", "line_total": 100}]})
        (line,) = doc["line_items"]
        self.assertEqual(line["description"], "Noodles")
        self.assertNotIn("description_raw", line)
        self.assertEqual(line["quantity"], 1)
        self.assertEqual(line["quantity_source"], "assumed")

    def test_build_does_not_mutate_input_lines(self):
        skeleton = {"line_items": [
            {"description": "Drink X2", "line_total": 100}]}
        build_document(skeleton)
        self.assertEqual(skeleton["line_items"][0], {"description": "Drink X2",
                                                    "line_total": 100})

    def test_build_defaults_missing_quantity(self):
        # Live S2 omission: model dropped quantity on a charge line.
        doc = build_document({"line_items": [
            {"description": "โลตัส ไอศกรีม ช็อกโกชิพ",
             "quantity": None, "line_total": 4000}]})
        (line,) = doc["line_items"]
        self.assertEqual(line["quantity"], 1)
        self.assertEqual(line["quantity_source"], "assumed")

    def test_build_keeps_explicit_quantity(self):
        for qty in (2, 0):
            doc = build_document({"line_items": [
                {"description": "Drink", "quantity": qty,
                 "line_total": 100}]})
            (line,) = doc["line_items"]
            self.assertEqual(line["quantity"], qty)
            self.assertNotIn("quantity_source", line)

    def test_build_qty_default_does_not_mutate_input(self):
        skeleton = {"line_items": [
            {"description": "Drink", "line_total": 100}]}
        build_document(skeleton)
        self.assertNotIn("quantity", skeleton["line_items"][0])

    def test_build_fills_legal_from_brand(self):
        doc = build_document({"issuer": {"legal_name": None,
                                         "brand_name": "Jones Salad"}})
        self.assertEqual(doc["issuer"]["legal_name"], "Jones Salad")

    def test_build_keeps_explicit_legal(self):
        doc = build_document({"issuer": {"legal_name": "บมจ.ปตท. น้ำมันและการค้าปลีก",
                                         "brand_name": "Cafe Amazon"}})
        self.assertEqual(doc["issuer"]["legal_name"],
                         "บมจ.ปตท. น้ำมันและการค้าปลีก")

    def test_build_legal_noop_without_brand(self):
        doc = build_document({"issuer": {"legal_name": None,
                                         "tax_id": "0105559141754"}})
        self.assertIsNone(doc["issuer"]["legal_name"])

    def test_build_does_not_mutate_input_issuer(self):
        skeleton = {"issuer": {"legal_name": None,
                               "brand_name": "Jones Salad"}}
        build_document(skeleton)
        self.assertIsNone(skeleton["issuer"]["legal_name"])

    def test_build_forces_no_claim_unless_full(self):
        # Glimmer emits form=unknown with can_claim=True (S6/S1): an
        # auto-posted VAT claim on an unproven slip. Only a proven
        # full invoice may claim; the guard only ever narrows to False.
        doc = build_document({"form": "abbreviated",
                              "can_claim_input_vat": True})
        self.assertFalse(doc["can_claim_input_vat"])
        doc = build_document({"form": "unknown",
                              "can_claim_input_vat": True})
        self.assertFalse(doc["can_claim_input_vat"])
        doc = build_document({"can_claim_input_vat": True})
        self.assertEqual(doc["form"], "unknown")
        self.assertFalse(doc["can_claim_input_vat"])

    def test_build_keeps_full_invoice_claim_choice(self):
        doc = build_document({"form": "full",
                              "can_claim_input_vat": True})
        self.assertTrue(doc["can_claim_input_vat"])
        doc = build_document({"form": "full",
                              "can_claim_input_vat": False})
        self.assertFalse(doc["can_claim_input_vat"])
        doc = build_document({"form": "full"})
        self.assertTrue(doc["can_claim_input_vat"])
        doc = build_document({"form": "unknown"})
        self.assertFalse(doc["can_claim_input_vat"])

    def test_export_row(self):
        row = to_row(fresh(), review_status="auto_accept")
        self.assertEqual(row["grand_total"], "107.00")
        self.assertEqual(row["can_claim_input_vat"], "no")  # ABB
        self.assertEqual(row["seller_tax_id"], "1234567890121")
        text = to_csv([row])
        self.assertEqual(text.splitlines()[0], ",".join(COLUMNS))
        self.assertIn("ABB-0001", text)

    def test_columns_match_spec_minimum(self):
        self.assertEqual(COLUMNS[:15], SPEC_MINIMUM_COLUMNS)
        self.assertEqual(COLUMNS[15], "note")


class TestExportBatch(unittest.TestCase):
    def _doc(self, tmp, name, doc_no):
        doc = fresh()
        doc["document_number"] = doc_no
        path = os.path.join(tmp, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        return path

    def test_batch_stdout_two_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = self._doc(tmp, "a.json", "ABB-0001")
            b = self._doc(tmp, "b.json", "ABB-0002")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_export(argparse.Namespace(
                    doc=[a, b], out="", seen="", append=False))
        self.assertEqual(rc, 0)
        lines = buf.getvalue().splitlines()
        self.assertEqual(lines[0], ",".join(COLUMNS))
        self.assertEqual(len(lines), 3)
        self.assertIn("ABB-0001", buf.getvalue())
        self.assertIn("ABB-0002", buf.getvalue())

    def test_append_grows_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = self._doc(tmp, "a.json", "ABB-0001")
            b = self._doc(tmp, "b.json", "ABB-0002")
            out = os.path.join(tmp, "ledger.csv")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cmd_export(argparse.Namespace(
                    doc=[a], out=out, seen="", append=False)), 0)
                self.assertEqual(cmd_export(argparse.Namespace(
                    doc=[b], out=out, seen="", append=True)), 0)
            with open(out, encoding="utf-8") as f:
                lines = f.read().splitlines()
        self.assertEqual(lines[0], ",".join(COLUMNS))
        self.assertEqual(len(lines), 3)

    def test_append_creates_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = self._doc(tmp, "a.json", "ABB-0001")
            out = os.path.join(tmp, "ledger.csv")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cmd_export(argparse.Namespace(
                    doc=[a], out=out, seen="", append=True)), 0)
            with open(out, encoding="utf-8") as f:
                content = f.read()
        self.assertTrue(content.startswith(",".join(COLUMNS)))
        self.assertIn("ABB-0001", content)

    def test_append_rejects_foreign_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = self._doc(tmp, "a.json", "ABB-0001")
            out = os.path.join(tmp, "ledger.csv")
            with open(out, "w", encoding="utf-8") as f:
                f.write("a,b,c\n1,2,3\n")
            err = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                rc = cmd_export(argparse.Namespace(
                    doc=[a], out=out, seen="", append=True))
            self.assertEqual(rc, 1)
            self.assertIn("header", err.getvalue())
            with open(out, encoding="utf-8") as f:
                self.assertEqual(f.read(), "a,b,c\n1,2,3\n")

    def test_batch_partial_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = self._doc(tmp, "a.json", "ABB-0001")
            out = os.path.join(tmp, "ledger.csv")
            seen = os.path.join(tmp, "seen.json")
            err = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                rc = cmd_export(argparse.Namespace(
                    doc=[a, a], out=out, seen=seen, append=False))
            with open(out, encoding="utf-8") as f:
                n_lines = len(f.read().splitlines())
        self.assertEqual(rc, 3)
        self.assertIn("duplicate", err.getvalue())
        self.assertEqual(n_lines, 2)

    def test_append_needs_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = self._doc(tmp, "a.json", "ABB-0001")
            err = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                rc = cmd_export(argparse.Namespace(
                    doc=[a], out="", seen="", append=True))
        self.assertEqual(rc, 2)
        self.assertIn("--out", err.getvalue())


if __name__ == "__main__":
    unittest.main()
