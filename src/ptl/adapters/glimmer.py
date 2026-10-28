"""Glimmer offline adapter: local Extractor+Reviewer+segment.

Same adapter interfaces and pipeline code, no telemetry/upload.
Accuracy reported separately as system D.
"""
from .base import Extractor, Reviewer, Segmenter
from ..pipeline.segment import Crop
from ..pipeline.triage import triage


class GlimmerSegmenter(Segmenter):
    def __init__(self, model_path=None):
        self.model_path = model_path

    def segment(self, image_path):
        raise NotImplementedError("wire local Glimmer segment model")


class GlimmerExtractor(Extractor):
    def __init__(self, model_path=None):
        self.model_path = model_path

    def extract(self, crop):
        raise NotImplementedError("wire local Glimmer extractor model")


class GlimmerReviewer(Reviewer):
    def review(self, doc, validation):
        return triage(doc, validation)
