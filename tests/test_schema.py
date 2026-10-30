import json
import os
import unittest

from ptl.pipeline.extract import build_document
from ptl.schema import (REQUIRED_TOP, check_structure, derive_claim_flag,
                        load_schema)
from tests.fixtures import SEEDS, fresh, fresh_seed

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "data",
                             "label.template.json")


class TestSchema(unittest.TestCase):
    def test_schema_file_parses(self):
        schema = load_schema()
        totals = schema["properties"]["totals"]["properties"]
        self.assertIn("grand_total", totals)
        self.assertIn("rounding_adjustment", totals)

    def test_label_template_parses(self):
        with open(TEMPLATE_PATH, encoding="utf-8") as f:
            template = json.load(f)
        for key in REQUIRED_TOP:
            self.assertIn(key, template)
        self.assertIn("grand_total", template["totals"])

    def test_golden_struct_valid(self):
        self.assertEqual(check_structure(fresh()), [])

    def test_missing_required(self):
        errs = check_structure({"document_type": "receipt"})
        self.assertTrue(any("schema_version" in e for e in errs))
        self.assertTrue(any("issuer" in e for e in errs))
        self.assertTrue(any("totals" in e for e in errs))

    def test_bad_type_and_version(self):
        d = fresh()
        d["schema_version"] = "9.9"
        d["document_type"] = "nonsense"
        errs = check_structure(d)
        self.assertEqual(len(errs), 2)

    def test_abb_unclaimable(self):
        d = derive_claim_flag({**fresh(), "form": "abbreviated"})
        self.assertFalse(d["can_claim_input_vat"])
        d = derive_claim_flag({**fresh(), "form": "full"})
        self.assertTrue(d["can_claim_input_vat"])

    def test_bad_status_rejected(self):
        d = dict(fresh(), status="ok")
        errors = check_structure(d)
        self.assertTrue(any("status" in e for e in errors), errors)
        d = dict(fresh(), status="unpaid")
        self.assertEqual(check_structure(d), [])

    def test_unknown_form_unclaimable(self):
        # derive_claim_flag used `form != "abbreviated"`, re-granting the
        # claim on unknown forms at CLI load: a form-unknown Glimmer doc
        # exported can_claim=yes. Only proven-full claims, matching the
        # build_document guard.
        d = derive_claim_flag({**fresh(), "form": "unknown"})
        self.assertFalse(d["can_claim_input_vat"])
        d = derive_claim_flag({k: v for k, v in fresh().items()
                               if k != "form"})
        self.assertFalse(d["can_claim_input_vat"])


class TestReferenceDialect(unittest.TestCase):
    """Document keys follow rapee/docs/03-extraction-schema.json.

    Paths below are hand-transcribed from the reference schema (plus the
    rounding_adjustment extension 05 section 12 calls for). The legacy
    sweep fails if any abbreviated platform-dialect key spelling survives
    in fixtures, extractor output, or the schema file.
    """

    PATHS = ["document_number", "document_type", "form",
             "issuer.tax_id", "issuer.legal_name",
             "dates.issue_date", "dates.raw_date_string",
             "dates.era_resolution.detected_era",
             "totals.grand_total", "totals.subtotal", "totals.total",
             "totals.vatable_amount", "totals.vat_amount",
             "totals.vat_amount_computed", "totals.discount_total",
             "totals.non_vatable_amount",
             "line_items.0.quantity", "line_items.0.quantity_source",
             "line_items.0.line_total", "payments.0.method",
             "payments.0.amount", "source.image_quality.blur_score"]

    LEGACY = ['"doc_no"', '"qty"', '"vat":', '"vatable"',
              '"discount":', '"non_vatable"', '"vat_computed"',
              '"rounding_adj"', '"issue":', '"incl"', '"excl"',
              '"embedded"', '"blur"', '"contrast"', '"skew"',
              '"tax_point"', '"due":', '"zero"']

    def _resolve(self, doc, dotted):
        cur = doc
        for part in dotted.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            elif (isinstance(cur, list) and part.isdigit()
                    and int(part) < len(cur)):
                cur = cur[int(part)]
            else:
                self.fail(f"missing reference path: {dotted}")
        return cur

    def test_reference_paths_present(self):
        doc = fresh()  # S1_GOLDEN carries every key incl. document_number
        for path in self.PATHS:
            with self.subTest(path=path):
                self._resolve(doc, path)
        self.assertEqual(doc["vat_mode"], "inclusive")
        self.assertEqual(doc["line_items"][2]["quantity_source"],
                         "embedded_in_name")
        built = build_document({"totals": {}})
        self.assertEqual(built["totals"]["rounding_adjustment"], 0)

    def test_anchors_are_strings_or_null(self):
        docs = [fresh()] + [fresh_seed(n) for n in SEEDS]
        for doc in docs:
            anchor = (doc.get("dates") or {}).get(
                "era_resolution", {}).get("anchor_used")
            self.assertTrue(anchor is None or isinstance(anchor, str),
                            f"bool anchor in {doc.get('document_number')}")

    def test_legacy_keys_absent(self):
        docs = [fresh(), build_document({})]
        docs += [fresh_seed(n) for n in SEEDS]
        blob = json.dumps(docs + [load_schema()])
        for legacy in self.LEGACY:
            with self.subTest(legacy=legacy):
                self.assertNotIn(legacy, blob)


if __name__ == "__main__":
    unittest.main()
