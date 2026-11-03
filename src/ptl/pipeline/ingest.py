"""Stage 0: ingest — EXIF strip, hashing, PII masking (PDPA)."""
import hashlib
import re

CARD_RE = re.compile(r"\d{4}[ -]?\d{2,6}[*xX]{2,}\d{0,4}|\d{4}[ -]?\*{4,}[ -]?\d{4}")
PHONE_RE = re.compile(r"(?<!\d)(0\d{1,2}[ -]?\d{3}[ -]?\d{3,4})(?!\d)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strip_exif(data: bytes) -> bytes:
    """Return JPEG bytes with EXIF APP1 segments removed (stdlib-only).

    Walks markers between SOI and SOS; drops APP1 segments whose payload
    starts with b"Exif\\x00\\x00" (the GPS-bearing phone metadata); copies
    everything else verbatim, including scan data from SOS to EOF.
    Non-JPEG input and truncated/corrupt headers pass through unchanged.
    """
    if len(data) < 4 or data[0:2] != b"\xff\xd8":
        return data
    out = bytearray(data[0:2])
    i, n = 2, len(data)
    while i + 1 < n:
        if data[i] != 0xFF:
            out += data[i:]
            return bytes(out)
        while i + 1 < n and data[i + 1] == 0xFF:  # fill bytes
            i += 1
        if i + 1 >= n:
            break
        code = data[i + 1]
        if code == 0xDA:  # SOS: scan data follows; copy to EOF verbatim
            out += data[i:]
            return bytes(out)
        if code in (0xD9, 0x01) or 0xD0 <= code <= 0xD7:
            out += data[i:i + 2]  # standalone markers
            i += 2
            continue
        if i + 3 >= n:
            out += data[i:]
            return bytes(out)
        seglen = (data[i + 2] << 8) + data[i + 3]
        if seglen < 2 or i + 2 + seglen > n:
            out += data[i:]
            return bytes(out)
        seg = data[i:i + 2 + seglen]
        is_exif = (code == 0xE1 and seglen >= 8
                   and seg[4:10] == b"Exif\x00\x00")
        if not is_exif:
            out += seg
        i += 2 + seglen
    out += data[i:]
    return bytes(out)


def strip_exif_note(path: str, stripped=False):
    """Record whether EXIF APP1 was removed before processing."""
    if stripped:
        return {"path": path, "exif_stripped": True,
                "note": "EXIF APP1 removed stdlib-only before processing"}
    return {"path": path, "exif_stripped": False,
            "note": "no EXIF APP1 found; bytes passed through"}


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
        **strip_exif_note(source_path, strip_exif(data) != data),
    }
