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


def image_dimensions(data):
    """Return (width, height) for PNG/JPEG bytes, else None.

    Stdlib-only header parse (no pixel decode): PNG reads IHDR,
    JPEG scans markers for the first SOF frame. Never raises:
    unparseable bytes mean region guidance is skipped and the
    extractor falls back to the whole image.
    """
    if not isinstance(data, (bytes, bytearray)) or len(data) < 30:
        return None
    raw = bytes(data)
    if raw[:8] == b"\x89PNG\r\n\x1a\n" and len(raw) >= 24:
        w = int.from_bytes(raw[16:20], "big")
        h = int.from_bytes(raw[20:24], "big")
        return (w, h) if w > 0 and h > 0 else None
    if raw[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 9 < len(raw):
        if raw[i] != 0xFF:
            i += 1
            continue
        marker = raw[i + 1]
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker == 0x01 or 0x02 <= marker <= 0xBF:
            i += 2
            continue
        size = int.from_bytes(raw[i + 2:i + 4], "big")
        if size < 2 or i + size + 2 > len(raw):
            return None
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC7,
                      0xC9, 0xCB, 0xCD, 0xCF):
            h = int.from_bytes(raw[i + 5:i + 7], "big")
            w = int.from_bytes(raw[i + 7:i + 9], "big")
            return (w, h) if w > 0 and h > 0 else None
        i += 2 + size
    return None


def crop_bbox_norm(crop, width, height):
    """Return the crop polygon bbox as (x0, y0, x1, y1) fractions.

    None when the polygon is empty or dimensions are missing: the
    caller then sends no region guidance.
    """
    poly = crop.polygon or []
    if not poly or not width or not height:
        return None
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]

    def frac(v, dim):
        return round(min(max(v / dim, 0.0), 1.0), 4)

    return (frac(min(xs), width), frac(min(ys), height),
            frac(max(xs), width), frac(max(ys), height))


def region_focus_text(crop, width, height):
    """Region clause appended to the extraction prompt, or "".

    Lets one photo hold several receipts: the extractor is told to
    transcribe only the receipt inside this crop's box, so per-crop
    extractions stop returning the same whole-image result.
    """
    box = crop_bbox_norm(crop, width, height)
    if box is None:
        return ""
    x0, y0, x1, y1 = box
    return (f"REGION: transcribe ONLY the receipt inside the box "
            f"(x0={x0}, y0={y0}, x1={x1}, y1={y1}) — fractions of "
            f"image width/height, origin top-left. Ignore all other "
            f"receipts, text and background outside this box.")


def pair_faded(crops):
    """Keep both original and faded-enhanced variants for review."""
    return [{"original": c.to_dict(), "enhanced": None} for c in crops]


def mark_partial(crops, indices):
    for c in crops:
        if c.index in set(indices):
            c.partial = True
    return crops


def box_cut_by_frame(x1, y1, x2, y2, width, height, margin_frac=0.01):
    """True when a box runs into the frame edge: the slip is cut off.

    Any side within margin_frac of the frame border marks a partial
    capture (05 sec 5 stage 1). Whole-frame boxes are NOT partial:
    they are the no-segmentation fallback, not a cut slip. Degenerate
    boxes and unknown dims judge nothing and return False.
    """
    if not width or not height or width <= 0 or height <= 0:
        return False
    if not (0 <= x1 < x2 and 0 <= y1 < y2):
        return False
    m = margin_frac
    if x1 <= width * m and y1 <= height * m:
        if x2 >= width * (1 - m) and y2 >= height * (1 - m):
            return False
    return (x1 <= width * m or y1 <= height * m
            or x2 >= width * (1 - m) or y2 >= height * (1 - m))
