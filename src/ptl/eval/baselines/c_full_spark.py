"""System C: full pipeline (segment + quality + Spark + R1-R14 + triage).

One validation-guided re-extraction fires while triage says
needs_review (see ptl.pipeline.retry); the per-crop dict records it
under "attempts" (1 = first reading accepted).
"""
from ptl.adapters.sam31 import Sam31Segmenter
from ptl.adapters.spark import SparkExtractor
from ptl.pipeline.quality import quality_gate
from ptl.pipeline.retry import retry_extract


def run(image_path, **kw):
    crops = Sam31Segmenter(**kw).segment(image_path)
    docs = []
    for crop in crops:
        q = crop.quality
        gate = quality_gate(q.get("blur"), q.get("contrast"),
                            q.get("skew"))
        if not gate.passed:
            docs.append({"crop": crop.index, "rejected": gate.to_dict()})
            continue
        doc, conf, validation, decision, used = retry_extract(
            crop, SparkExtractor(**kw))
        doc["field_confidence"] = conf
        docs.append({"crop": crop.index, "doc": doc,
                     "validation": validation, "triage": decision,
                     "attempts": used})
    return docs
