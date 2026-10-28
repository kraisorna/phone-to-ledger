import unittest

from ptl.pipeline.extract import (build_document,
                                  normalise_pos_identifier,
                                  split_embedded_qty, strip_vat_flag)
from ptl.pipeline.ingest import content_hash, mask_pii
from ptl.pipeline.quality import quality_gate
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


if __name__ == "__main__":
    unittest.main()
