"""End-to-end: image -> segment -> extract -> validate -> triage -> rows.

One photo per receipt: the Spark extractor sends the whole source image
(no crop rendering yet), so multi-crop photos cost one extraction per
crop and in-run R10 dedup collapses identical results. Pass
segmenter=/extractor= fakes in tests; defaults hit Meta Model API.
"""
from ..pipeline.dedup import SeenStore
from ..pipeline.export import to_csv, to_row
from ..pipeline.ingest import ingest_bytes
from ..pipeline.triage import triage
from ..pipeline.validate_rules import HARD_RULES, validate
from ..schema import check_structure, derive_claim_flag

NO_RECEIPTS = "no_receipts_found"


def _default_segmenter(api_key=None, concept="receipt"):
    from ..adapters.sam31 import Sam31Segmenter
    return Sam31Segmenter(api_key=api_key, concept=concept)


def _default_extractor(api_key=None):
    from ..adapters.spark import SparkExtractor
    return SparkExtractor(api_key=api_key)


def run_e2e(image_path, segmenter=None, extractor=None, seen_store=None):
    """Run the full pipeline; return a JSON-able result dict.

    seen_store: SeenStore or None (an in-memory store is used so
    duplicates still collapse within the run; the caller saves it).
    """
    segmenter = segmenter if segmenter is not None else _default_segmenter()
    extractor = extractor if extractor is not None else _default_extractor()
    store = seen_store if seen_store is not None else SeenStore()
    with open(image_path, "rb") as f:
        data = f.read()
    result = {"image": str(image_path), "ingest": ingest_bytes(data, str(image_path)),
              "crops": [], "docs": [], "rows": [], "csv": "", "note": ""}
    crops = segmenter.segment(str(image_path))
    result["crops"] = [c.to_dict() for c in crops]
    if not crops:
        result["note"] = NO_RECEIPTS
        result["csv"] = to_csv([])
        return result
    for crop in crops:
        doc, _conf = extractor.extract(crop)
        doc = derive_claim_flag(doc)
        source = doc.get("source")
        if isinstance(source, dict):
            source.setdefault("crop_index", crop.index)
            source.setdefault("image_uri", str(image_path))
        entry = {"crop_index": crop.index, "doc": doc,
                 "structure_errors": [], "validation": None,
                 "triage": None, "excluded": ""}
        struct_errors = check_structure(doc)
        if struct_errors:
            entry["structure_errors"] = struct_errors
            entry["triage"] = {"decision": "needs_review",
                               "reason": "structure errors",
                               "suggested_regions": []}
            entry["excluded"] = "structure errors: never exported"
            result["docs"].append(entry)
            continue
        validation = validate(doc, store.to_seen())
        entry["validation"] = validation
        entry["triage"] = triage(doc, validation)
        if not validation["rules"]["R10"]["pass"]:
            entry["excluded"] = ("duplicate: "
                                 + validation["rules"]["R10"]["detail"])
            result["docs"].append(entry)
            continue
        status = ("needs_review" if validation["requires_human_review"]
                  else "auto_accept")
        hard = [r for r in validation.get("hard_failed", [])
                if r in HARD_RULES]
        if hard:
            status = "blocked:" + ",".join(hard)
        else:
            store.record(doc)
        result["rows"].append(to_row(doc, review_status=status))
        result["docs"].append(entry)
    result["csv"] = to_csv(result["rows"])
    return result
