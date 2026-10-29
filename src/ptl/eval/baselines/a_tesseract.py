"""System A: Tesseract tha+eng + regex (no segmentation, no validation)."""
from ptl.adapters.tesseract import TesseractExtractor


def run(image_path, lang="tha+eng"):
    ext = TesseractExtractor(lang=lang)
    return ext.parse(ext.ocr(image_path))
