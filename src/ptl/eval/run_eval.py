"""Eval runner: score a preds file against a labels dir.

preds: JSON object {doc_id: doc} or list of {doc_id, doc}.
labels: dir of {doc_id}.json gold docs.
faded ids: text file, one doc_id per line.
"""
import argparse
import json
import os

from ptl.eval.score import aggregate, score_doc
from ptl.pipeline.triage import triage
from ptl.pipeline.validate_rules import validate
from ptl.schema import check_structure


def load_preds(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data
    return {d["doc_id"]: d.get("doc", d) for d in data}


def load_labels(d):
    labels = {}
    for name in sorted(os.listdir(d)):
        if name.endswith(".json"):
            with open(os.path.join(d, name), encoding="utf-8") as f:
                labels[name[:-5]] = json.load(f)
    return labels


def write_labels(out_dir, seeds):
    """Write {doc_id}.json gold files for a {doc_id: doc} mapping.

    The hand seeds are the eval gold: deterministic bytes (sorted
    keys, indent 2), so regeneration is a no-op diff. Returns the
    sorted list of doc ids written.
    """
    os.makedirs(out_dir, exist_ok=True)
    for doc_id in sorted(seeds):
        with open(os.path.join(out_dir, f"{doc_id}.json"), "w",
                  encoding="utf-8") as f:
            json.dump(seeds[doc_id], f, ensure_ascii=False, indent=2,
                      sort_keys=True)
            f.write("\n")
    return sorted(seeds)


def _flagged(pred):
    """Would the pipeline flag this pred? Same validate+triage, no API.

    Struct-invalid, missing-shaped, or rule-crashing preds count as
    flagged: unscorable output must go to review, never auto-accept.
    """
    try:
        if not isinstance(pred, dict) or check_structure(pred):
            return True
        v = validate(pred)
        return triage(pred, v)["decision"] != "auto_accept"
    except Exception:
        return True


def run_eval(preds_path, labels_path, faded_ids_path=""):
    preds = load_preds(preds_path)
    labels = load_labels(labels_path)
    faded = frozenset()
    if faded_ids_path:
        with open(faded_ids_path, encoding="utf-8") as f:
            faded = frozenset(l.strip() for l in f if l.strip())
    scored = []
    for doc_id, gold in sorted(labels.items()):
        pred = preds.get(doc_id, {})
        s = score_doc(pred, gold)
        s["doc_id"] = doc_id
        s["flagged"] = True if doc_id not in preds else _flagged(pred)
        scored.append(s)
    report = aggregate(scored, faded)
    report["missing_preds"] = sorted(set(labels) - set(preds))
    report["review"] = _review_crosstab(scored)
    return report


def _review_crosstab(scored):
    """05 sec 8 items 4-5: review rate, auto-accept accuracy, flag recall."""
    n = len(scored)
    flagged = [s for s in scored if s["flagged"]]
    auto = [s for s in scored if not s["flagged"]]
    wrong = [s for s in scored if not s["all_correct"]]
    auto_right = [s for s in auto if s["all_correct"]]
    wrong_flagged = [s for s in wrong if s["flagged"]]
    return {
        "n": n,
        "flagged": len(flagged),
        "review_rate": len(flagged) / n if n else None,
        "auto_accepted": len(auto),
        "auto_accept_all_correct": len(auto_right),
        "auto_accept_accuracy": (len(auto_right) / len(auto)
                                 if auto else None),
        "wrong": len(wrong),
        "wrong_flagged": len(wrong_flagged),
        "flag_recall": (len(wrong_flagged) / len(wrong)
                        if wrong else None),
        "flagged_ids": [s["doc_id"] for s in flagged],
        "wrong_unflagged_ids": [s["doc_id"] for s in wrong
                                if not s["flagged"]],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="ptl eval runner")
    p.add_argument("--preds", required=True)
    p.add_argument("--labels", required=True)
    p.add_argument("--faded-ids", default="")
    args = p.parse_args(argv)
    print(json.dumps(run_eval(args.preds, args.labels, args.faded_ids),
                     indent=2))


if __name__ == "__main__":
    main()
