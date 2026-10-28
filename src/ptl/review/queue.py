"""Human review queue: side-by-side image + doc, corrections => labels."""
import json
import os

from ..schema import check_structure


class ReviewQueue:
    def __init__(self, root):
        self.root = root
        os.makedirs(root, exist_ok=True)

    def _path(self, doc_id):
        return os.path.join(self.root, f"{doc_id}.json")

    def enqueue(self, doc_id, doc, validation, triage_decision):
        rec = {"doc_id": doc_id, "doc": doc, "validation": validation,
               "triage": triage_decision, "status": "pending",
               "correction": None}
        with open(self._path(doc_id), "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        return rec

    def resolve(self, doc_id, correction):
        with open(self._path(doc_id), encoding="utf-8") as f:
            rec = json.load(f)
        rec["status"] = "resolved"
        rec["correction"] = correction
        with open(self._path(doc_id), "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        return rec

    def pending(self):
        out = []
        for name in sorted(os.listdir(self.root)):
            if name.endswith(".json"):
                with open(os.path.join(self.root, name), encoding="utf-8") as f:
                    rec = json.load(f)
                if rec.get("status") == "pending":
                    out.append(rec)
        return out

    def _read_record(self, name):
        with open(os.path.join(self.root, name), encoding="utf-8") as f:
            return json.load(f)

    def get(self, doc_id):
        """Return one full record by doc id (raises if missing)."""
        return self._read_record(f"{doc_id}.json")

    def export_labels(self, labels_dir):
        """Write resolved corrections as run_eval labels ({doc_id}.json).

        Only human-verified corrections become ground truth: pending
        records and structurally invalid corrections are skipped, never
        exported. Returns {"exported": [...], "skipped": {id: reason}}.
        The queue stays the source of truth; re-export overwrites.
        """
        os.makedirs(labels_dir, exist_ok=True)
        exported, skipped = [], {}
        for name in sorted(os.listdir(self.root)):
            if not name.endswith(".json"):
                continue
            try:
                rec = self._read_record(name)
            except (OSError, ValueError):
                skipped[name] = "unreadable"
                continue
            doc_id = rec.get("doc_id") or name[:-5]
            if rec.get("status") != "resolved":
                skipped[doc_id] = "pending"
                continue
            correction = rec.get("correction")
            if not isinstance(correction, dict):
                skipped[doc_id] = "no correction"
                continue
            errors = check_structure(correction)
            if errors:
                skipped[doc_id] = "invalid: " + "; ".join(errors)
                continue
            with open(os.path.join(labels_dir, f"{doc_id}.json"), "w",
                      encoding="utf-8") as f:
                json.dump(correction, f, ensure_ascii=False, indent=2)
            exported.append(doc_id)
        return {"exported": exported, "skipped": skipped}
