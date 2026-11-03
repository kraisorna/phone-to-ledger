"""End-to-end: image -> segment -> extract -> validate -> triage -> rows.

One extraction per crop: the Spark extractor sends the whole source
image plus a REGION clause scoping the prompt to the crop's box, so
multi-receipt photos yield one doc per slip (live-verified on a
synthetic 2-up). In-run R10 dedup still collapses identical results.
Pass segmenter=/extractor= fakes in tests; defaults hit Meta Model API.
"""
import os
import tempfile
import time

from ..adapters.pricing import estimate_usd, usd_to_thb
from ..pipeline.dedup import SeenStore
from ..pipeline.export import to_csv, to_row
from ..pipeline.ingest import ingest_bytes, strip_exif
from ..pipeline.retry import retry_extract
from ..pipeline.triage import triage
from ..pipeline.validate_rules import HARD_RULES, validate
from ..review.queue import ReviewQueue
from ..schema import check_structure, derive_claim_flag


class _ClaimingExtractor:
    """Wrap an extractor so every attempt carries a settled claim flag.

    R14 judges the VAT claim; deriving per attempt (not just on the
    winner) lets best-reading selection compare settled readings.
    """

    def __init__(self, extractor):
        self._wrapped = extractor

    def extract(self, source):
        doc, conf = self._wrapped.extract(source)
        return derive_claim_flag(doc), conf

NO_RECEIPTS = "no_receipts_found"


def _default_segmenter(api_key=None, concept="receipt"):
    from ..adapters.sam31 import Sam31Segmenter
    return Sam31Segmenter(api_key=api_key, concept=concept)


def _default_extractor(api_key=None):
    from ..adapters.spark import SparkExtractor
    return SparkExtractor(api_key=api_key)


def _queue_id(doc, crop_index):
    raw = doc.get("document_number") or f"crop-{crop_index}"
    return str(raw).replace("/", "_").replace("\\", "_")


_ZERO_STATS = {"calls": 0, "input_tokens": 0, "output_tokens": 0,
               "reasoning_tokens": 0, "seconds": 0.0}


def _stats_of(adapter):
    """Snapshot an adapter's .stats (zeros when uninstrumented).

    Adds estimated_usd from the official pay-as-you-go rates when the
    adapter's model is priced, else None (never a silent partial),
    plus the THB conversion of that leg.
    """
    stats = getattr(adapter, "stats", None)
    if not isinstance(stats, dict):
        stats = {}
    snap = dict(_ZERO_STATS)
    snap.update({k: stats.get(k, snap[k]) for k in snap})
    snap["estimated_usd"] = estimate_usd(getattr(adapter, "model", None),
                                         snap)
    snap["estimated_thb"] = usd_to_thb(snap["estimated_usd"])
    return snap


def run_e2e(image_path, segmenter=None, extractor=None, seen_store=None,
            review_queue=None, attempts=2):
    """Run the full pipeline; return a JSON-able result dict.

    seen_store: SeenStore or None (an in-memory store is used so
    duplicates still collapse within the run; the caller saves it).
    review_queue: dir path or None; flagged (non-auto_accept) docs are
    enqueued for human review. R10 duplicates are excluded, not queued.
    attempts: extraction attempts per crop (validation-guided retry;
    clean first readings still cost 1 call).
    """
    segmenter = segmenter if segmenter is not None else _default_segmenter()
    extractor = extractor if extractor is not None else _default_extractor()
    store = seen_store if seen_store is not None else SeenStore()
    queue = ReviewQueue(review_queue) if review_queue else None
    with open(image_path, "rb") as f:
        data = f.read()
    # Adapters only ever see EXIF-scrubbed bytes (phone GPS stays home);
    # provenance below still names the original photo.
    stripped = strip_exif(data)
    work_path, tmp_path = str(image_path), None
    if stripped != data:
        suffix = os.path.splitext(str(image_path))[1] or ".jpg"
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        tmp.write(stripped)
        tmp.close()
        work_path, tmp_path = tmp.name, tmp.name
    start = time.monotonic()
    try:
        result = _run_crops(image_path, work_path, segmenter, extractor,
                            store, queue, data,
                            scrubbed=tmp_path is not None, attempts=attempts)
    finally:
        if tmp_path is not None:
            os.unlink(tmp_path)
    seg, ext = _stats_of(segmenter), _stats_of(extractor)
    legs = (seg["estimated_usd"], ext["estimated_usd"])
    usd_total = (round(legs[0] + legs[1], 6) if None not in legs
                 else None)
    result["usage"] = {"segment": seg, "extract": ext,
                       "estimated_usd_total": usd_total,
                       "estimated_thb_total": usd_to_thb(usd_total)}
    result["elapsed_seconds"] = time.monotonic() - start
    return result


def _run_crops(image_path, work_path, segmenter, extractor, store,
               queue, data, scrubbed=False, attempts=2):
    result = {"image": str(image_path), "ingest": ingest_bytes(data, str(image_path)),
              "crops": [], "docs": [], "rows": [], "csv": "", "note": "",
              "review_enqueued": []}
    crops = segmenter.segment(work_path)
    result["crops"] = [c.to_dict() for c in crops]
    for c in result["crops"]:
        c["image_path"] = str(image_path)
    # The R10 image leg is cross-run only: every crop of this photo
    # shares its hash, so within-run comparisons must use the loaded
    # hashes, never hashes recorded earlier in this same run (content
    # and doc keys still collapse true within-run duplicates).
    loaded_hashes = set(store.image_hashes)
    if not crops:
        result["note"] = NO_RECEIPTS
        result["csv"] = to_csv([])
        return result
    for crop in crops:
        doc, _conf, _v, _d, used = retry_extract(
            crop, _ClaimingExtractor(extractor), attempts=attempts)
        source = doc.get("source") if isinstance(doc, dict) else None
        if isinstance(source, dict):
            source.setdefault("crop_index", crop.index)
            source.setdefault("image_uri", str(image_path))
            if scrubbed:
                # The model echoes the filename it saw; the scrubbed
                # temp copy is deleted after the run, so provenance
                # must name the original photo, never the temp path.
                source["image_uri"] = os.path.basename(str(image_path))
            # The hash of the photo bytes is a fact the pipeline
            # knows and the model can only leave null or garble; the
            # R10 exact-image leg depends on it, so always stamp the
            # original-file hash (strip-proof across runs).
            source["image_hash"] = result["ingest"]["image_hash"]
        entry = {"crop_index": crop.index, "doc": doc, "attempts": used,
                 "structure_errors": [], "validation": None,
                 "triage": None, "excluded": ""}
        struct_errors = check_structure(doc)
        if struct_errors:
            entry["structure_errors"] = struct_errors
            entry["triage"] = {"decision": "needs_review",
                               "reason": "structure errors",
                               "suggested_regions": []}
            entry["excluded"] = "structure errors: never exported"
            if queue is not None:
                qid = _queue_id(doc, crop.index)
                queue.enqueue(qid, doc, None, entry["triage"])
                result["review_enqueued"].append(qid)
            result["docs"].append(entry)
            continue
        seen = store.to_seen()
        seen["image_hashes"] = loaded_hashes
        validation = validate(doc, seen)
        entry["validation"] = validation
        entry["triage"] = triage(doc, validation)
        if crop.partial:
            # The slip runs into the frame edge: never extracted as
            # complete (05 sec 5 stage 1). The reading stays available
            # for the reviewer, but the doc always needs review.
            entry["triage"] = {
                "decision": "needs_review",
                "reason": ("partial capture: slip cut off by frame; "
                           + entry["triage"]["reason"]),
                "suggested_regions": entry["triage"]["suggested_regions"]}
        if not validation["rules"]["R10"]["pass"]:
            entry["excluded"] = ("duplicate: "
                                 + validation["rules"]["R10"]["detail"])
            result["docs"].append(entry)
            continue
        if queue is not None and entry["triage"]["decision"] != "auto_accept":
            qid = _queue_id(doc, crop.index)
            queue.enqueue(qid, doc, validation, entry["triage"])
            result["review_enqueued"].append(qid)
        status = ("needs_review" if (validation["requires_human_review"]
                  or entry["triage"]["decision"] != "auto_accept")
                  else "auto_accept")
        hard = [r for r in validation.get("hard_failed", [])
                if r in HARD_RULES]
        if hard:
            status = "blocked:" + ",".join(hard)
        else:
            store.record(doc)
        note = ("partial capture — retake photo" if crop.partial else "")
        result["rows"].append(to_row(doc, review_status=status, note=note))
        result["docs"].append(entry)
    result["csv"] = to_csv(result["rows"])
    return result
