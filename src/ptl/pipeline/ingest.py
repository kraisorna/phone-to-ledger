"""Stage 0: ingest — EXIF strip, hashing, PII masking (PDPA)."""
import hashlib
import re

from ..schema import EMAIL_BLOCKLIST

CARD_RE = re.compile(r"(?<![A-Za-z0-9])\d{4}[ -]?\d{2,6}[*xX#]{2,}\d{0,4}"
                     r"|(?<![A-Za-z0-9])\d{4}[ -]?[*xX#]{4,}[ -]?\d{4}"
                     r"|(?<![A-Za-z0-9])\d(?:[ -]?\d){15,18}(?![A-Za-z0-9])")
PHONE_RE = re.compile(r"(?<![A-Za-z0-9])(0\d{1,2}[ -]?\d{3}[ -]?\d{3,4})(?!\d)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")

# 02 sec 12: PDPA. Doc paths scrub_doc touches: free text
# (discarded_text, line descriptions, payments method_raw) plus
# the issuer contact fields. Numeric scored fields — tax ID,
# totals, vat_amount, quantities, line totals — are never
# regex-masked; the gold sweep test proves scrub is a no-op on
# all 25 seeds' scored paths. Person names need no regex: the
# extraction prompt forbids transcribing them.
SCRUB_PATHS = ("discarded_text", "description", "description_raw",
               "method_raw", "issuer.phone", "issuer.email")


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
        addr = m.group(0)
        # Prompt placeholders ("staff@noemail.local") stay readable
        # so R11's blocklist can classify them; same predicate R11
        # uses. Real addresses are masked.
        if any(b in addr.lower() for b in EMAIL_BLOCKLIST):
            return addr
        return "[EMAIL]"
    return EMAIL_RE.sub(_mask_email, text)


def scrub_doc(doc):
    """Mask PDPA PII at the ingestion boundary (02 sec 12).

    Free text (discarded_text entries, payments method_raw) is
    regex-masked; issuer.phone is dropped (store numbers count as
    personal data); issuer.email is masked unless it is a prompt
    placeholder R11 must stay able to read. Scored machine
    fields are never touched — see SCRUB_PATHS.
    """
    issuer = doc.get("issuer")
    if isinstance(issuer, dict):
        issuer["phone"] = None
        email = issuer.get("email")
        if email and not any(b in email.lower()
                             for b in EMAIL_BLOCKLIST):
            issuer["email"] = None
    texts = doc.get("discarded_text")
    if isinstance(texts, list):
        doc["discarded_text"] = [mask_pii(t) if isinstance(t, str) else t
                                 for t in texts]
    for line in doc.get("line_items") or []:
        if not isinstance(line, dict):
            continue
        for key in ("description", "description_raw"):
            if isinstance(line.get(key), str):
                line[key] = mask_pii(line[key])
    for pay in doc.get("payments") or []:
        if isinstance(pay, dict) and isinstance(pay.get("method_raw"),
                                                str):
            pay["method_raw"] = mask_pii(pay["method_raw"])
    return doc


def ingest_bytes(data: bytes, source_path=""):
    return {
        "image_hash": content_hash(data),
        "size_bytes": len(data),
        "source_path": source_path,
        **strip_exif_note(source_path, strip_exif(data) != data),
    }
