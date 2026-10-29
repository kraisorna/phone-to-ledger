"""System A: Tesseract tha+eng + regex (no segmentation, no validation)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from ptl.adapters.tesseract import TesseractExtractor  # noqa: E402


def run(image_path, lang="tha+eng"):
    ext = TesseractExtractor(lang=lang)
    return ext.parse(ext.ocr(image_path))
