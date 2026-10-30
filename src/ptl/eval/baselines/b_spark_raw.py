"""System B: single-prompt Spark: no segmentation, no post-processing,
no validation."""
from ptl.adapters.spark import SparkExtractor


def run(crop, **kw):
    return SparkExtractor(**kw).extract(crop, postprocess=False)
