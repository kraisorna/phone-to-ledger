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
from .triage import DECIDE_AUTO, triage
from .validate_rules import validate


def _failed_count(validation):
    return sum(1 for v in (validation.get("rules") or {}).values()
               if not v.get("pass"))


def retry_extract(source, extractor, attempts=2):
    """Extract up to `attempts` times; return the best reading.

    Returns (doc, conf, validation, triage_decision, attempts_used).
    Stops early on auto_accept. `attempts` below 1 is a ValueError.
    """
    if attempts < 1:
        raise ValueError(f"attempts must be >= 1, got {attempts}")
    best, used = None, 0
    for used in range(1, attempts + 1):
        doc, conf = extractor.extract(source)
        validation = validate(doc)
        decision = triage(doc, validation)
        if best is None or _failed_count(validation) < _failed_count(best[2]):
            best = (doc, conf, validation, decision)
        if decision.get("decision") == DECIDE_AUTO:
            break
    return best + (used,)
