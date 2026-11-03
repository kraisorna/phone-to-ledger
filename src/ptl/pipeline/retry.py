"""Validation-guided extraction retry: re-ask, never rewrite.

VLM reads flip run to run while the print stays fixed (S1 branch
00031/2083, S4 60G/GOG, S2 date/legal measured live), so when triage
says needs_review one fresh extraction is worth trying before a human
is involved. The retry keeps the attempt with fewer failed rules and
keeps the FIRST on ties, so a retry that fixes nothing cannot swap
values. It never clears a failure: the winner's real validation and
triage ship with it, and a still-failing doc still goes to review.
Cost is bounded: clean docs cost 1 call, flagged docs at most
`attempts` (default 2).
"""
from .triage import DECIDE_AUTO, DECIDE_REVIEW, triage
from .validate_rules import validate


def _failed_count(validation):
    return sum(1 for v in (validation.get("rules") or {}).values()
               if not v.get("pass"))


def retry_extract(source, extractor, attempts=2):
    """Extract up to `attempts` times; return the best reading.

    Returns (doc, conf, validation, triage_decision, attempts_used).
    Stops early on auto_accept. `attempts` below 1 is a ValueError.
    A malformed reading (extract or validate raising) spends one
    attempt and is skipped; when every attempt is malformed the
    last reading returns with validation None and a needs_review
    decision, so one bad image degrades to review instead of
    raising.
    """
    if attempts < 1:
        raise ValueError(f"attempts must be >= 1, got {attempts}")
    best, used, last_doc = None, 0, None
    for used in range(1, attempts + 1):
        try:
            doc, conf = extractor.extract(source)
        except Exception:  # noqa: BLE001 - malformed reading, retry
            continue
        if isinstance(doc, dict):
            last_doc = doc
        try:
            validation = validate(doc)
            decision = triage(doc, validation)
        except Exception:  # noqa: BLE001 - unvalidatable reading, retry
            continue
        if best is None or _failed_count(validation) < _failed_count(best[2]):
            best = (doc, conf, validation, decision)
        if decision.get("decision") == DECIDE_AUTO:
            break
    if best is not None:
        return best + (used,)
    return (last_doc if isinstance(last_doc, dict) else {},
            {}, None,
            {"decision": DECIDE_REVIEW, "reason": "structure errors",
             "suggested_regions": []}, used)
