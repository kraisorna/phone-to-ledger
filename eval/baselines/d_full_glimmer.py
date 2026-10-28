"""System D: full offline pipeline (Glimmer local models)."""
from ptl.adapters.glimmer import (GlimmerExtractor, GlimmerReviewer,
                                  GlimmerSegmenter)
from ptl.pipeline.quality import quality_gate
from ptl.pipeline.validate_rules import validate


def run(image_path, **kw):
    crops = GlimmerSegmenter(**kw).segment(image_path)
    docs = []
    for crop in crops:
        q = crop.quality
        gate = quality_gate(q.get("blur"), q.get("contrast"),
                            q.get("skew"))
        if not gate.passed:
            docs.append({"crop": crop.index, "rejected": gate.to_dict()})
            continue
        doc, conf = GlimmerExtractor(**kw).extract(crop)
        doc["field_confidence"] = conf
        validation = validate(doc)
        docs.append({"crop": crop.index, "doc": doc,
                     "validation": validation,
                     "triage": GlimmerReviewer().review(doc, validation)})
    return docs
