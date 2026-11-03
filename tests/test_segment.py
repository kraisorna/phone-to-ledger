"""Segment helpers: stdlib image dimensions + region focus text.

Multi-receipt photos need per-crop extraction guidance without pixel
libraries: dimensions come from a header parse, and the crop bbox is
sent to the extractor as normalized coordinates.
"""
import unittest

from ptl.pipeline.segment import (Crop, box_cut_by_frame, crop_bbox_norm,
                                  image_dimensions, region_focus_text)


def _png(w, h):
    return (b"\x89PNG\r\n\x1a\n" + (13).to_bytes(4, "big") + b"IHDR"
            + w.to_bytes(4, "big") + h.to_bytes(4, "big") + b"\x08\x02"
            + b"\x00" * 10)


def _jpg(w, h):
    sof = (b"\xff\xc0\x00\x0b\x08" + h.to_bytes(2, "big")
           + w.to_bytes(2, "big") + b"\x01")
    app0 = b"\xff\xe0\x00\x10" + b"\x00" * 14
    return b"\xff\xd8" + app0 + sof + b"\x00" * 20


class TestImageDimensions(unittest.TestCase):
    def test_png_ihdr(self):
        self.assertEqual(image_dimensions(_png(640, 480)), (640, 480))

    def test_jpeg_sof_after_app0(self):
        self.assertEqual(image_dimensions(_jpg(1376, 3084)),
                         (1376, 3084))

    def test_garbage_returns_none(self):
        self.assertIsNone(image_dimensions(b"x" * 40))
        self.assertIsNone(image_dimensions(b"\xff\xd8" + b"\x00" * 40))
        self.assertIsNone(image_dimensions(b"short"))
        self.assertIsNone(image_dimensions(None))
        self.assertIsNone(image_dimensions("not-bytes" * 10))


class TestRegionFocus(unittest.TestCase):
    def test_bbox_normalized(self):
        crop = Crop(index=0,
                    polygon=[[10, 20], [110, 20], [110, 220], [10, 220]])
        self.assertEqual(crop_bbox_norm(crop, 200, 400),
                         (0.05, 0.05, 0.55, 0.55))

    def test_bbox_clamped(self):
        crop = Crop(index=0, polygon=[[-50, -50], [500, 500]])
        self.assertEqual(crop_bbox_norm(crop, 200, 200),
                         (0.0, 0.0, 1.0, 1.0))

    def test_empty_polygon_no_text(self):
        crop = Crop(index=0, polygon=[])
        self.assertIsNone(crop_bbox_norm(crop, 200, 200))
        self.assertEqual(region_focus_text(crop, 200, 200), "")

    def test_missing_dims_no_text(self):
        crop = Crop(index=0, polygon=[[0, 0], [10, 10]])
        self.assertIsNone(crop_bbox_norm(crop, None, None))
        self.assertEqual(region_focus_text(crop, None, None), "")

    def test_focus_text_names_box(self):
        crop = Crop(index=1, polygon=[[0, 0], [100, 50]])
        text = region_focus_text(crop, 200, 100)
        self.assertIn("x0=0.0, y0=0.0, x1=0.5, y1=0.5", text)
        self.assertIn("ONLY", text)


class TestCutByFrame(unittest.TestCase):
    # 05 sec 5 stage 1: a slip cut off by the frame is marked partial.
    W, H = 1000, 2000

    def test_each_edge_cuts(self):
        cut = box_cut_by_frame
        self.assertTrue(cut(0, 500, 400, 1500, self.W, self.H))
        self.assertTrue(cut(600, 500, 1000, 1500, self.W, self.H))
        self.assertTrue(cut(300, 0, 700, 1500, self.W, self.H))
        self.assertTrue(cut(300, 500, 700, 2000, self.W, self.H))

    def test_interior_box_clean(self):
        self.assertFalse(box_cut_by_frame(300, 500, 700, 1500,
                                          self.W, self.H))

    def test_margin_scales_with_frame(self):
        # 1% of 1000x2000: 9px in is cut, 11px in is clean.
        self.assertTrue(box_cut_by_frame(9, 500, 700, 1500, self.W, self.H))
        self.assertFalse(box_cut_by_frame(11, 500, 700, 1500,
                                          self.W, self.H))

    def test_whole_frame_is_fallback_not_partial(self):
        self.assertFalse(box_cut_by_frame(0, 0, 1000, 2000, self.W, self.H))
        self.assertFalse(box_cut_by_frame(2, 3, 995, 1990, self.W, self.H))

    def test_degenerate_judges_nothing(self):
        self.assertFalse(box_cut_by_frame(5, 5, 5, 9, self.W, self.H))
        self.assertFalse(box_cut_by_frame(9, 5, 5, 9, self.W, self.H))
        self.assertFalse(box_cut_by_frame(300, 500, 700, 1500, 0, 0))
        self.assertFalse(box_cut_by_frame(300, 500, 700, 1500, None, None))


if __name__ == "__main__":
    unittest.main()
