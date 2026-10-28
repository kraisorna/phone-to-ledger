"""Agent triage over rule results.

The agent may re-ask a region, explain, and decide auto_accept|needs_review.
It may NOT edit values to pass, clear an R1-R6 fail, or guess: uncertain
=> needs_review.
"""
from .validate_rules import HARD_RULES

DECIDE_AUTO = "auto_accept"
DECIDE_REVIEW = "needs_review"


def triage(doc, validation):
    failed = [r for r, v in (validation.get("rules") or {}).items()
              if not v.get("pass")]
    if any(r in HARD_RULES for r in failed):
        return {"decision": DECIDE_REVIEW,
                "reason": f"hard fail: {sorted(set(failed) & HARD_RULES)}",
                "suggested_regions": failed}
    if failed:
        return {"decision": DECIDE_REVIEW,
                "reason": f"soft fail: {sorted(failed)}",
                "suggested_regions": failed}
    conf = doc.get("field_confidence") or {}
    if any(v < 0.5 for v in conf.values()):
        return {"decision": DECIDE_REVIEW,
                "reason": "low field confidence",
                "suggested_regions": sorted(conf)}
    return {"decision": DECIDE_AUTO, "reason": "all rules pass",
            "suggested_regions": []}
