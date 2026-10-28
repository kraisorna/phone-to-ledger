"""SAM3.1 segmenter adapter (stub: wire model endpoint here)."""
from .base import Segmenter
from ..pipeline.segment import Crop


class Sam31Segmenter(Segmenter):
    def __init__(self, endpoint=None):
        self.endpoint = endpoint

    def segment(self, image_path):
        raise NotImplementedError(
            "wire SAM3.1 endpoint; return [Crop(index=0, polygon=[...])]")
