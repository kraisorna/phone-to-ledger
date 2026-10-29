"""System C: full pipeline (segment + quality + Spark + R1-R12 + triage)."""
from ptl.adapters.sam31 import Sam31Segmenter
from ptl.adapters.spark import SparkExtractor
from ptl.pipeline.quality import quality_gate
from ptl.pipeline.triage import triage
from ptl.pipeline.validate_rules import validate


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
        doc, conf = SparkExtractor(**kw).extract(crop)
        doc["field_confidence"] = conf
        validation = validate(doc)
        docs.append({"crop": crop.index, "doc": doc,
                     "validation": validation,
                     "triage": triage(doc, validation)})
    return docs
