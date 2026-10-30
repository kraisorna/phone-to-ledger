"""Stage 3: validation rules R1-R14 as pure functions.

R13 (completeness floor) is a platform extension past 05's R1-R12: every
other rule skips on missing data, so without it an empty extraction
passes everything and auto-posts. Soft severity like R7/R11/R12 — an
incomplete doc needs a human, not a block.
R14 (form resolved) is the same kind of extension: an unknown form
means the VAT-claim decision is unproven, so a human must confirm it.

Each rule returns (passed: bool, detail: str). `validate(doc, seen=None)`
runs all rules and returns the schema `validation` block.
R1-R6 fail => never auto-post.
"""
import datetime
import re

from ..money import vat_inclusive
from ..schema import EMAIL_BLOCKLIST

CARD_UNMASKED_RE = re.compile(r"(?<!\d)\d{13,19}(?!\d)")
LOW_CONF_THRESHOLD = 0.5
LOW_CONF_FIELDS = ("totals.grand_total", "totals.vat_amount",
                   "dates.issue_date", "issuer.tax_id",
                   "document_number")

# Rules whose failure blocks auto-post.
HARD_RULES = {"R1", "R2", "R3", "R4", "R5", "R6"}


def _totals(doc):
    return doc.get("totals") or {}


def _lines(doc):
    return [li for li in (doc.get("line_items") or [])
            if not li.get("is_section_header")]


def _charge_lines(doc):
    return [li for li in _lines(doc)
            if not li.get("is_category_subtotal")]


def r1_line_sum(doc):
    """sum(charge lines) - discount_total + rounding_adjustment == subtotal."""
    t = _totals(doc)
    if t.get("subtotal") is None:
        return True, "no subtotal present; skipped"
    expect = sum(li.get("line_total", 0) for li in _charge_lines(doc))
    expect -= (t.get("discount_total") or 0)
    expect += (t.get("rounding_adjustment") or 0)
    if abs(expect - t["subtotal"]) <= 1:
        return True, (f"lines-discount_total+rounding_adjustment={expect} "
                      f"subtotal={t['subtotal']}")
    return False, (f"lines-discount_total+rounding_adjustment={expect} "
                   f"!= subtotal={t['subtotal']}")


def r2_grand(doc):
    """subtotal (+service charge) == grand total."""
    t = _totals(doc)
    if t.get("subtotal") is None or t.get("grand_total") is None:
        return True, "subtotal/grand missing; skipped"
    expect = t["subtotal"] + (t.get("service_charge") or 0)
    if abs(expect - t["grand_total"]) <= 1:
        return True, f"subtotal+svc={expect} grand={t['grand_total']}"
    return False, f"subtotal+svc={expect} != grand={t['grand_total']}"


def r3_vat_inclusive(doc):
    """vat_amount == round(grand*7/107) +-1 satang when vat_mode=inclusive."""
    t = _totals(doc)
    if doc.get("vat_mode") != "inclusive":
        return True, f"vat_mode={doc.get('vat_mode')}; skipped"
    if t.get("vat_amount") is None or t.get("grand_total") is None:
        return True, "vat_amount/grand missing; skipped"
    expect = vat_inclusive(t["grand_total"],
                           doc.get("vat_rate_bp", 700))
    if abs(expect - t["vat_amount"]) <= 1:
        return True, f"vat_amount={t['vat_amount']} computed={expect}"
    return False, f"vat_amount={t['vat_amount']} != computed={expect}"


def r4_vat_split(doc):
    """vatable_amount + vat_amount == grand (when both present)."""
    t = _totals(doc)
    if t.get("vatable_amount") is None or t.get("vat_amount") is None:
        return True, "vatable_amount/vat_amount missing; skipped"
    expect = (t["vatable_amount"] + t["vat_amount"]
              + (t.get("non_vatable_amount") or 0))
    grand = t.get("grand_total")
    if grand is None:
        return True, "grand missing; skipped"
    if abs(expect - grand) <= 1:
        return True, f"vatable_amount+vat_amount+nonvat={expect} grand={grand}"
    return False, (f"vatable_amount+vat_amount+nonvat={expect} "
                   f"!= grand={grand}")


def r5_payments(doc):
    """sum(payments) == grand unless unpaid/partial."""
    t = _totals(doc)
    pays = doc.get("payments") or []
    grand = t.get("grand_total")
    if grand is None:
        return True, "grand missing; skipped"
    if not pays:
        if doc.get("status") in (None, "", "unpaid", "issued", "draft",
                                 "partially_paid"):
            return True, "no payments; treated as unpaid/partial"
        return False, f"no payments but status={doc.get('status')!r}"
    total = sum(p.get("amount", 0) for p in pays)
    if abs(total - grand) <= 1:
        return True, f"payments={total} grand={grand}"
    if doc.get("status") == "partially_paid":
        return True, f"partial payments={total} grand={grand}"
    return False, f"payments={total} != grand={grand}"


def thai_tax_id_check(tax_id):
    """13-digit Thai tax ID checksum: s=sum d_i*(13-i), check=(11-s%11)%10."""
    if not tax_id or not re.fullmatch(r"\d{13}", tax_id):
        return False
    digits = [int(c) for c in tax_id]
    s = sum(d * (13 - i) for i, d in enumerate(digits[:12]))
    return (11 - s % 11) % 10 == digits[12]


def r6_tax_id(doc):
    """issuer tax_id (when present) is a valid 13-digit checksum."""
    tax_id = (doc.get("issuer") or {}).get("tax_id")
    if not tax_id:
        if (doc.get("issuer") or {}).get("is_individual"):
            return True, "individual without tax_id; skipped"
        return True, "no issuer tax_id; skipped"
    if thai_tax_id_check(tax_id):
        return True, f"tax_id {tax_id} checksum ok"
    return False, f"tax_id {tax_id!r} bad format/checksum"


def r7_dates(doc):
    """doc date resolved, not in the future, not older than 5 years."""
    dates = doc.get("dates") or {}
    issue = dates.get("issue_date")
    era = (dates.get("era_resolution") or {}).get("detected_era")
    anchor = (dates.get("era_resolution") or {}).get("anchor_used")
    if era == "ambiguous" and not anchor:
        return False, "ambiguous era without anchor"
    if not issue:
        return True, "no issue date; skipped"
    try:
        day = datetime.date.fromisoformat(issue[:10])
    except ValueError:
        return False, f"unparseable issue date {issue!r}"
    today = datetime.date.today()
    if day > today:
        return False, f"issue {issue} is in the future"
    if day < today - datetime.timedelta(days=5 * 365 + 2):
        return False, f"issue {issue} older than 5 years"
    return True, f"issue {issue} ok"


def r8_modifiers(doc):
    """every modifier has exactly one parent line number."""
    lines = {li.get("line_number") for li in (doc.get("line_items") or [])}
    for li in (doc.get("line_items") or []):
        if li.get("is_modifier"):
            parent = li.get("parent_line_number")
            if parent is None or parent not in lines:
                return False, f"modifier line {li.get('line_number')} bad parent {parent!r}"
    return True, "modifiers ok"


def r9_category_subtotals(doc):
    """category subtotal rows must be flagged so they are not double-counted."""
    for li in (doc.get("line_items") or []):
        desc = (li.get("description") or "").lower()
        looks_subtotal = ("subtotal" in desc or "sub total" in desc
                          or "ยอดรวมย่อย" in desc)
        if looks_subtotal and not li.get("is_category_subtotal"):
            return False, f"unflagged subtotal row: {li.get('description')!r}"
    return True, "category subtotals ok"


def dup_keys(doc):
    """R10 lookup keys for a doc; a key is None when unusable.

    Shared by r10_duplicates (check) and the SeenStore (record) so the
    two can never disagree on what counts as the same document.
    """
    issuer = doc.get("issuer") or {}
    tax_id = issuer.get("tax_id")
    doc_number = doc.get("document_number")
    doc_key = (tax_id, doc_number) if (tax_id and doc_number) else None
    fuzzy = (tax_id, (doc.get("dates") or {}).get("issue_date"),
             _totals(doc).get("grand_total"), doc.get("pos_identifier"))
    fuzzy_key = fuzzy if all(v is not None for v in fuzzy) else None
    image_hash = (doc.get("source") or {}).get("image_hash") or None
    return {"doc_key": doc_key, "fuzzy_key": fuzzy_key,
            "image_hash": image_hash}


def r10_duplicates(doc, seen=None):
    """duplicate keys: (tax_id, document_number), (tax_id, date, total, pos),
    image hash."""
    seen = seen or {}
    keys = dup_keys(doc)
    if (keys["doc_key"] is not None
            and keys["doc_key"] in seen.get("doc_keys", set())):
        return False, f"duplicate (tax_id, document_number)={keys['doc_key']}"
    if (keys["fuzzy_key"] is not None
            and keys["fuzzy_key"] in seen.get("fuzzy_keys", set())):
        return False, f"duplicate (tax_id, date, total, pos)={keys['fuzzy_key']}"
    if (keys["image_hash"] is not None
            and keys["image_hash"] in seen.get("image_hashes", set())):
        return False, "duplicate image hash"
    return True, "no duplicate keys"


def r11_suspicious(doc):
    """rate != 7%, out-of-range money, placeholder email, bad branch, unmasked card."""
    if doc.get("vat_rate_bp", 700) not in (700, 0):
        return False, f"suspicious vat_rate_bp={doc.get('vat_rate_bp')}"
    grand = _totals(doc).get("grand_total")
    if grand is not None and grand > 100_000_000_00:  # > 100M THB
        return False, f"suspicious grand_total={grand}"
    email = ((doc.get("issuer") or {}).get("email") or "").lower()
    if email and any(b in email for b in EMAIL_BLOCKLIST):
        return False, f"placeholder email {email!r}"
    branch = (doc.get("issuer") or {}).get("branch_code")
    # 5-digit codes are the Revenue Dept norm, but CP Axtra/Lotus's slips
    # print 4-digit store codes (S2 "1681", S7 "6662" live): accept 4-5.
    if branch and not re.fullmatch(r"\d{4,5}", branch):
        return False, f"branch_code {branch!r} not 4-5 digits"
    blob = " ".join([(doc.get("issuer") or {}).get("address") or ""]
                    + (doc.get("discarded_text") or []))
    if CARD_UNMASKED_RE.search(blob):
        return False, "possible unmasked card number in text"
    return True, "no suspicious signals"


def r12_low_confidence(doc):
    """money/date/tax_id confidence below threshold => review."""
    conf = doc.get("field_confidence") or {}
    low = [f for f in LOW_CONF_FIELDS
           if f in conf and conf[f] < LOW_CONF_THRESHOLD]
    if low:
        return False, f"low confidence: {', '.join(low)}"
    return True, "confidence ok"


def r13_completeness(doc):
    """grand_total > 0, >=1 line item, issue_date present => else review."""
    grand = _totals(doc).get("grand_total")
    if not isinstance(grand, (int, float)) or grand <= 0:
        return False, f"grand_total missing or non-positive: {grand!r}"
    if not doc.get("line_items"):
        return False, "no line items"
    if not (doc.get("dates") or {}).get("issue_date"):
        return False, "issue_date missing"
    return True, "grand, lines, and date present"


def r14_form_resolved(doc):
    """form is full|abbreviated; unknown/missing => review."""
    form = doc.get("form")
    if form in ("full", "abbreviated"):
        return True, f"form {form}"
    return False, f"form {form!r} unresolved; VAT claim unproven"


RULES = {"R1": r1_line_sum, "R2": r2_grand, "R3": r3_vat_inclusive,
         "R4": r4_vat_split, "R5": r5_payments, "R6": r6_tax_id,
         "R7": r7_dates, "R8": r8_modifiers, "R9": r9_category_subtotals,
         "R10": r10_duplicates, "R11": r11_suspicious,
         "R12": r12_low_confidence, "R13": r13_completeness,
         "R14": r14_form_resolved}


def validate(doc, seen=None):
    """Run R1-R14; return the schema `validation` block dict."""
    results, failed, hard_failed = {}, [], []
    for name in sorted(RULES):
        if name == "R10":
            passed, detail = RULES[name](doc, seen)
        else:
            passed, detail = RULES[name](doc)
        results[name] = {"pass": passed, "detail": detail}
        if not passed:
            failed.append(name)
            if name in HARD_RULES:
                hard_failed.append(name)
    return {
        "rules": results,
        "requires_human_review": bool(failed),
        "review_reasons": [f"{r}: {results[r]['detail']}" for r in failed],
        "hard_failed": hard_failed,
    }
