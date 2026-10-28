"""Stage 0: ingest — EXIF strip, hashing, PII masking (PDPA)."""
import hashlib
import re

CARD_RE = re.compile(r"\d{4}[ -]?\d{2,6}[*xX]{2,}\d{0,4}|\d{4}[ -]?\*{4,}[ -]?\d{4}")
PHONE_RE = re.compile(r"(?<!\d)(0\d{1,2}[ -]?\d{3}[ -]?\d{3,4})(?!\d)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strip_exif_note(path: str):
    """Record that EXIF must be stripped before storage.

    Real stripping needs Pillow (ImageOps.exif_transpose + re-save without
    exif); this returns the ingest record so the pipeline works stdlib-only
    and the adapter fills in pixels when Pillow is available.
    """
    return {"path": path, "exif_stripped": False,
            "note": "strip EXIF with Pillow before persisting"}


def mask_pii(text: str) -> str:
    if not text:
        return text
    text = CARD_RE.sub("[CARD]", text)
    text = PHONE_RE.sub("[PHONE]", text)

    def _mask_email(m):
        user, _, domain = m.group(0).partition("@")
        return "[EMAIL]"
    return EMAIL_RE.sub(_mask_email, text)


def ingest_bytes(data: bytes, source_path=""):
    return {
        "image_hash": content_hash(data),
        "size_bytes": len(data),
        "source_path": source_path,
        **strip_exif_note(source_path),
    }
