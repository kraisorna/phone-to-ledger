"""USD estimates for e2e usage: priced models exact, unknown never partial.

Rates mirror the official pricing page (fetched 2026-11-02):
https://dev.meta.ai/docs/pricing-rate-limits
"""
import unittest

from ptl.adapters.pricing import USD_THB_AS_OF, estimate_usd, usd_to_thb
from ptl.api.e2e import run_e2e
from tests.fixtures import fresh_seed
from tests.test_e2e import _crop, _Ext, _image_file, _Seg


class TestPricing(unittest.TestCase):
    def test_spark_standard(self):
        stats = {"calls": 1, "input_tokens": 4987, "output_tokens": 2180,
                 "seconds": 11.5}
        self.assertEqual(estimate_usd("muse-spark-1.3", stats), 0.015499)

    def test_spark_contributor(self):
        stats = {"calls": 1, "input_tokens": 1000000,
                 "output_tokens": 1000000, "seconds": 1.0}
        self.assertEqual(estimate_usd("muse-spark-1.3-contributor", stats),
                         0.30)

    def test_sam_per_image(self):
        stats = {"calls": 3, "input_tokens": 0, "output_tokens": 0,
                 "seconds": 2.0}
        self.assertEqual(estimate_usd("sam-3.1", stats), 0.0075)

    def test_local_models_free(self):
        stats = {"calls": 1, "input_tokens": 9, "output_tokens": 9,
                 "seconds": 1.0}
        self.assertEqual(estimate_usd("muse-glimmer", stats), 0.0)
        self.assertEqual(estimate_usd("tesseract", stats), 0.0)

    def test_unknown_is_none(self):
        stats = {"calls": 1, "input_tokens": 9, "output_tokens": 9,
                 "seconds": 1.0}
        self.assertIsNone(estimate_usd("mystery-model", stats))
        self.assertIsNone(estimate_usd(None, stats))
        self.assertIsNone(estimate_usd("muse-spark-1.3", {}))


class TestE2eCost(unittest.TestCase):
    def test_priced_run_total(self):
        import os
        p = _image_file()
        try:
            seg, ext = _Seg([_crop()]), _Ext([fresh_seed("S1")])
            seg.model = "sam-3.1"
            seg.stats = {"calls": 1, "input_tokens": 0, "output_tokens": 0,
                         "seconds": 7.3}
            ext.model = "muse-spark-1.3"
            ext.stats = {"calls": 1, "input_tokens": 4987,
                         "output_tokens": 2180, "seconds": 11.5}
            res = run_e2e(p, segmenter=seg, extractor=ext, attempts=1)
        finally:
            os.unlink(p)
        self.assertEqual(res["usage"]["segment"]["estimated_usd"], 0.0025)
        self.assertEqual(res["usage"]["extract"]["estimated_usd"], 0.015499)
        self.assertEqual(res["usage"]["estimated_usd_total"], 0.017999)

    def test_unpriced_run_total_none(self):
        import os
        p = _image_file()
        try:
            res = run_e2e(p, segmenter=_Seg([_crop()]),
                          extractor=_Ext([fresh_seed("S1")]), attempts=1)
        finally:
            os.unlink(p)
        self.assertIsNone(res["usage"]["segment"]["estimated_usd"])
        self.assertIsNone(res["usage"]["estimated_usd_total"])


class TestThb(unittest.TestCase):
    def test_conversion_rounds_to_satang(self):
        # Pinned 33.65 THB/USD (2026-11-01): the smoke-#72 receipt's
        # $0.017999 is about 61 satang, kept to 2 decimals.
        self.assertEqual(usd_to_thb(0.017999), 0.61)
        self.assertEqual(usd_to_thb(0.0025), 0.08)
        self.assertEqual(usd_to_thb(0.0), 0.0)

    def test_none_stays_none(self):
        self.assertIsNone(usd_to_thb(None))

    def test_rate_pin_is_dated(self):
        self.assertRegex(USD_THB_AS_OF, r"^20[0-9]{2}-[0-9]{2}-[0-9]{2}$")

    def test_e2e_legs_and_total(self):
        import os
        p = _image_file()
        try:
            seg, ext = _Seg([_crop()]), _Ext([fresh_seed("S1")])
            seg.model = "sam-3.1"
            seg.stats = {"calls": 1, "input_tokens": 0, "output_tokens": 0,
                         "seconds": 7.3}
            ext.model = "muse-spark-1.3"
            ext.stats = {"calls": 1, "input_tokens": 4987,
                         "output_tokens": 2180, "seconds": 11.5}
            res = run_e2e(p, segmenter=seg, extractor=ext, attempts=1)
            plain = run_e2e(p, segmenter=_Seg([_crop()]),
                            extractor=_Ext([fresh_seed("S1")]), attempts=1)
        finally:
            os.unlink(p)
        self.assertEqual(res["usage"]["segment"]["estimated_thb"], 0.08)
        self.assertEqual(res["usage"]["extract"]["estimated_thb"], 0.52)
        self.assertEqual(res["usage"]["estimated_thb_total"], 0.61)
        self.assertIsNone(plain["usage"]["segment"]["estimated_thb"])
        self.assertIsNone(plain["usage"]["estimated_thb_total"])


if __name__ == "__main__":
    unittest.main()
