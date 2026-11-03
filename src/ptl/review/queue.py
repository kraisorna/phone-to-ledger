"""Human review queue: side-by-side image + doc, corrections => labels."""
import json
import os
from html import escape

from ..money import to_thb
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


def to_html(rec, image_uri=None):
    """Render one record as a side-by-side review page (02 sec 14).

    Source image left, extracted fields + rule failures right. Pure
    stdlib string building; every interpolated value is escaped.
    image_uri overrides the record's extraction-time uri (often a
    bare basename) so the reviewer can point at the real scan.
    """
    doc = rec.get("doc") or {}
    validation = rec.get("validation") or {}
    triage = rec.get("triage") or {}
    issuer = doc.get("issuer") or {}
    totals = doc.get("totals") or {}
    dates = doc.get("dates") or {}
    source = doc.get("source") or {}
    pays = doc.get("payments") or []
    decision = triage.get("decision", "needs_review")
    banner = ("green" if decision == "auto_accept" else "red")
    fields = [
        ("seller", issuer.get("legal_name") or ""),
        ("brand", issuer.get("brand_name") or ""),
        ("tax_id", issuer.get("tax_id") or ""),
        ("branch", issuer.get("branch_code") or ""),
        ("document_number", doc.get("document_number") or ""),
        ("issue_date", dates.get("issue_date") or ""),
        ("form", doc.get("form") or ""),
        ("grand_total", to_thb(totals.get("grand_total"))),
        ("vat", to_thb(totals.get("vat_amount"))),
        ("vatable", to_thb(totals.get("vatable_amount"))),
        ("payments", "+".join(p.get("method", "") for p in pays)),
        ("pos", doc.get("pos_identifier") or ""),
        ("lines", str(len(doc.get("line_items") or []))),
    ]
    rows = "".join(
        f"<tr><th>{escape(k)}</th><td>{escape(v)}</td></tr>"
        for k, v in fields)
    failed = "".join(
        f"<li><b>{escape(name)}</b>: {escape(v.get('detail', ''))}</li>"
        for name, v in sorted((validation.get("rules") or {}).items())
        if not v.get("pass"))
    reasons = "".join(
        f"<li>{escape(r)}</li>"
        for r in validation.get("review_reasons", []))
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>review {escape(rec.get("doc_id", ""))}</title>
<style>body{{font-family:sans-serif;margin:1em}}
.banner{{padding:.5em;color:white;background:{banner}}}
.wrap{{display:flex;gap:1em}}.wrap img{{max-width:45%}}
table{{border-collapse:collapse}}th,td{{
border:1px solid #ccc;padding:.2em .5em;text-align:left}}
.fail{{color:red}}</style></head>
<body><h1 class="banner">{escape(decision)}: \
{escape(rec.get("doc_id", ""))}</h1>
<div class="wrap"><img src="{escape(image_uri or source.get("image_uri", ""))}" \
alt="source receipt">
<div><h2>extracted fields</h2><table>{rows}</table>
<h2 class="fail">failed rules</h2><ul>{failed}</ul>
<h2>review reasons</h2><ul>{reasons}</ul>
<h2>triage</h2><p>{escape(triage.get("reason", ""))}</p>
</div></div>
<details><summary>full record JSON</summary><pre>{escape(json.dumps(
    rec, ensure_ascii=False, indent=2))}</pre></details>
</body></html>
"""
