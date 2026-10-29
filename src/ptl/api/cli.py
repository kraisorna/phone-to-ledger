"""`ptl` CLI: ingest / validate / export / eval / review."""
import argparse
import json
import sys

from ..eval.run_eval import run_eval
from ..pipeline.dedup import SeenStore
from ..pipeline.ingest import ingest_bytes, mask_pii
from ..pipeline.triage import triage
from ..pipeline.validate_rules import validate
from ..pipeline.export import append_csv, to_csv, to_row
from ..review.queue import ReviewQueue
from ..schema import check_structure, derive_claim_flag


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def cmd_ingest(args):
    with open(args.image, "rb") as f:
        data = f.read()
    print(json.dumps(ingest_bytes(data, args.image), indent=2))


def cmd_validate(args):
    doc = derive_claim_flag(_load_json(args.doc))
    struct_errors = check_structure(doc)
    out = {"structure_errors": struct_errors}
    if struct_errors and not args.force:
        print(json.dumps(out, indent=2))
        return 1
    seen = SeenStore.load(args.seen).to_seen() if args.seen else None
    validation = validate(doc, seen)
    out["validation"] = validation
    out["triage"] = triage(doc, validation)
    print(json.dumps(out, indent=2))
    return 0 if not validation["requires_human_review"] else 2


def cmd_export(args):
    docs = args.doc if isinstance(args.doc, list) else [args.doc]
    if args.append and not args.out:
        print("export --append needs --out", file=sys.stderr)
        return 2
    store = SeenStore.load(args.seen) if args.seen else None
    rows = []
    excluded = 0
    recorded = 0
    for path in docs:
        doc = derive_claim_flag(_load_json(path))
        validation = validate(doc, store.to_seen() if store else None)
        if not validation["rules"]["R10"]["pass"]:
            # Duplicates are excluded with a note, never silently
            # merged: no ledger row, JSON note on stderr. Re-run
            # without --seen to force-export a false positive.
            print(json.dumps({"excluded": "duplicate: "
                              + validation["rules"]["R10"]["detail"]}),
                  file=sys.stderr)
            excluded += 1
            continue
        status = ("needs_review" if validation["requires_human_review"]
                  else "auto_accept")
        if any(r in validation.get("hard_failed", []) for r in ("R1", "R2", "R3", "R4", "R5", "R6")):
            status = "blocked:" + ",".join(validation["hard_failed"])
        if store is not None and not validation.get("hard_failed"):
            store.record(doc)
            recorded += 1
        rows.append(to_row(doc, review_status=status))
    if store is not None and recorded:
        store.save(args.seen)
    if not rows:
        return 3
    if args.append:
        try:
            append_csv(args.out, rows)
        except ValueError as e:
            print(f"export: {e}", file=sys.stderr)
            return 1
    elif args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(to_csv(rows))
    else:
        sys.stdout.write(to_csv(rows))
    return 3 if excluded else 0


def cmd_eval(args):
    report = run_eval(args.preds, args.labels, faded_ids_path=args.faded_ids)
    print(json.dumps(report, indent=2))
    return 0


def cmd_review(args):
    queue = ReviewQueue(args.queue)
    if args.pending:
        compact = [{"doc_id": r.get("doc_id"),
                    "decision": (r.get("triage") or {}).get("decision"),
                    "reasons": (r.get("validation") or {}).get(
                        "review_reasons", [])}
                   for r in queue.pending()]
        print(json.dumps(compact, indent=2, ensure_ascii=False))
        return 0
    if args.show:
        try:
            rec = queue.get(args.show)
        except (OSError, ValueError) as e:
            print(f"cannot show {args.show}: {e}", file=sys.stderr)
            return 1
        print(json.dumps(rec, indent=2, ensure_ascii=False))
        return 0
    if args.resolve:
        if not args.correction:
            print("resolve needs --correction FILE", file=sys.stderr)
            return 1
        try:
            correction = _load_json(args.correction)
        except (OSError, ValueError) as e:
            print(f"cannot load correction: {e}", file=sys.stderr)
            return 1
        try:
            rec = queue.resolve(args.resolve, correction)
        except OSError as e:
            print(f"cannot resolve {args.resolve}: {e}", file=sys.stderr)
            return 1
        print(json.dumps({"doc_id": rec["doc_id"], "status": rec["status"]},
                         indent=2))
        return 0
    if args.export_labels:
        print(json.dumps(queue.export_labels(args.export_labels), indent=2))
        return 0
    print("review needs one of --pending, --show, --resolve, --export-labels",
          file=sys.stderr)
    return 1


def build_parser():
    p = argparse.ArgumentParser(prog="ptl", description="phone-to-ledger CLI")
    sub = p.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("ingest", help="hash + EXIF note for an image")
    pi.add_argument("image")
    pi.set_defaults(func=cmd_ingest)
    pv = sub.add_parser("validate", help="run R1-R12 + triage on a doc JSON")
    pv.add_argument("--doc", required=True)
    pv.add_argument("--force", action="store_true")
    pv.add_argument("--seen", default="",
                    help="seen-store JSON for R10 duplicate check")
    pv.set_defaults(func=cmd_validate)
    pe = sub.add_parser("export", help="export doc JSON(s) to ledger CSV")
    pe.add_argument("--doc", required=True, nargs="+",
                    help="one or more doc JSON paths")
    pe.add_argument("--out", default="")
    pe.add_argument("--seen", default="",
                    help="seen-store JSON: exclude recorded dups (exit 3), "
                         "record accepted docs")
    pe.add_argument("--append", action="store_true",
                    help="append rows to --out instead of overwriting it")
    pe.set_defaults(func=cmd_export)
    pg = sub.add_parser("eval", help="score preds vs labels")
    pg.add_argument("--preds", required=True)
    pg.add_argument("--labels", required=True)
    pg.add_argument("--faded-ids", default="")
    pg.set_defaults(func=cmd_eval)
    pr = sub.add_parser("review", help="human review queue operations")
    pr.add_argument("--queue", required=True)
    pr.add_argument("--pending", action="store_true",
                    help="list pending records (compact)")
    pr.add_argument("--show", default="",
                    help="print one full record by doc id")
    pr.add_argument("--resolve", default="",
                    help="resolve doc id with --correction FILE")
    pr.add_argument("--correction", default="")
    pr.add_argument("--export-labels", default="",
                    help="export resolved corrections to a labels dir")
    pr.set_defaults(func=cmd_review)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
