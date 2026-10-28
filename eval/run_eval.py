"""Eval runner: score a preds file against a labels dir.

preds: JSON object {doc_id: doc} or list of {doc_id, doc}.
labels: dir of {doc_id}.json gold docs.
faded ids: text file, one doc_id per line.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from eval.score import aggregate, score_doc  # noqa: E402


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
        scored.append(s)
    report = aggregate(scored, faded)
    report["missing_preds"] = sorted(set(labels) - set(preds))
    return report


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
