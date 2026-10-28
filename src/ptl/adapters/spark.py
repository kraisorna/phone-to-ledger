"""Muse Spark extractor adapter (stub: wire model endpoint here)."""
from .base import Extractor


class SparkExtractor(Extractor):
    def __init__(self, model="spark-1.3", endpoint=None):
        self.model = model
        self.endpoint = endpoint

    def extract(self, crop):
        raise NotImplementedError(
            "wire Spark endpoint with EXTRACTION_PROMPT_RULES; "
            "return build_document(raw) + confidences")
