"""Scorer: JSON-vs-JSON field accuracy + doc-all-correct + faded split.

Primary fields (exact unless noted):
  tax_id / branch_code / document_number / form exact; legal_name
  normalised exact; dates.issue_date exact ISO; money exact satang;
  lines (desc, quantity, total) F1.
Also: doc-all-correct counts + %, faded subset, review% + auto-accept
accuracy, latency/cost passthrough. n=50: report counts, not just rates.
"""
import re
import unicodedata

MONEY_FIELDS = ("totals.grand_total", "totals.subtotal",
                "totals.vat_amount", "totals.vatable_amount",
                "totals.total", "totals.discount_total")
EXACT_FIELDS = ("issuer.tax_id", "issuer.branch_code", "document_number",
                "form", "dates.issue_date")


def _get(doc, dotted):
    cur = doc
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def normalise_legal(name):
    if name is None:
        return None
    s = unicodedata.normalize("NFKC", name).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def score_lines(pred_items, gold_items):
    """F1 over (normalised desc, quantity, line_total) triples."""
    def key(li):
        return (normalise_legal(li.get("description")),
                li.get("quantity"), li.get("line_total"))
    p = [key(li) for li in (pred_items or [])
         if not li.get("is_section_header")]
    g = [key(li) for li in (gold_items or [])
         if not li.get("is_section_header")]
    g_multiset = list(g)
    tp = 0
    for k in p:
        if k in g_multiset:
            tp += 1
            g_multiset.remove(k)
    prec = tp / len(p) if p else (1.0 if not g else 0.0)
    rec = tp / len(g) if g else 1.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {"precision": prec, "recall": rec, "f1": f1, "tp": tp,
            "n_pred": len(p), "n_gold": len(g)}


def score_doc(pred, gold):
    """Return {fields: {name: bool}, lines: {...}, all_correct: bool}."""
    fields = {}
    for f in EXACT_FIELDS:
        pv, gv = _get(pred, f), _get(gold, f)
        fields[f] = (pv == gv) and not (pv is None and gv is not None)
    for f in MONEY_FIELDS:
        gv = _get(gold, f)
        if gv is None:
            continue
        fields[f] = _get(pred, f) == gv
    fields["issuer.legal_name"] = (
        normalise_legal(_get(pred, "issuer.legal_name"))
        == normalise_legal(_get(gold, "issuer.legal_name")))
    lines = score_lines(pred.get("line_items"), gold.get("line_items"))
    fields["lines.f1_exact"] = lines["f1"] == 1.0
    return {"fields": fields, "lines": lines,
            "all_correct": all(fields.values())}


def aggregate(scored, faded_ids=frozenset()):
    """Aggregate per-doc scores; faded_ids selects the faded subset."""
    def _agg(items):
        n = len(items)
        if not n:
            return {"n": 0}
        # Union of scored fields: a money field absent from one gold doc
        # (e.g. S2's missing VAT line) is skipped for that doc only, and
        # each field's accuracy uses its own denominator (reported counts).
        field_names = sorted({f for s in items for f in s["fields"]})
        per_field, per_field_n = {}, {}
        for f in field_names:
            scored = [s for s in items if f in s["fields"]]
            per_field[f] = sum(1 for s in scored if s["fields"][f])
            per_field_n[f] = len(scored)
        return {"n": n,
                "per_field_counts": per_field,
                "per_field_n": per_field_n,
                "per_field_acc": {f: per_field[f] / per_field_n[f]
                                  for f in field_names},
                "doc_all_correct": sum(1 for s in items if s["all_correct"]),
                "mean_lines_f1": sum(s["lines"]["f1"] for s in items) / n}
    all_r = _agg(scored)
    faded = _agg([s for s in scored if s["doc_id"] in faded_ids])
    return {"overall": all_r, "faded": faded,
            "faded_ids": sorted(faded_ids)}
