"""Adapter interfaces shared by cloud and offline backends."""
from abc import ABC, abstractmethod


class Segmenter(ABC):
    @abstractmethod
    def segment(self, image_path):
        """Return list of Crop records."""


class Extractor(ABC):
    @abstractmethod
    def extract(self, crop):
        """Return (schema doc dict, per-field confidence dict)."""


class Reviewer(ABC):
    @abstractmethod
    def review(self, doc, validation):
        """Return triage decision dict."""
