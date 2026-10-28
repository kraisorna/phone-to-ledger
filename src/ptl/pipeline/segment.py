"""Stage 1: segmentation interface + crop records.

Real segmentation is done by the SAM3.1 adapter; this module holds the
crop data model and helpers (deskew notes, faded enhancement pairing).
"""
from dataclasses import dataclass, field


@dataclass
class Crop:
    index: int
    polygon: list  # [[x, y], ...] in source pixels
    deskewed: bool = False
    enhanced_for_faded: bool = False
    partial: bool = False  # partial capture: mark, never extract as complete
    quality: dict = field(default_factory=dict)
    image_path: str = ""  # source file; empty when pixels unavailable

    def to_dict(self):
        return {
            "index": self.index, "polygon": self.polygon,
            "deskewed": self.deskewed,
            "enhanced_for_faded": self.enhanced_for_faded,
            "partial": self.partial, "quality": self.quality,
            "image_path": self.image_path,
        }


def pair_faded(crops):
    """Keep both original and faded-enhanced variants for review."""
    return [{"original": c.to_dict(), "enhanced": None} for c in crops]


def mark_partial(crops, indices):
    for c in crops:
        if c.index in set(indices):
            c.partial = True
    return crops
