"""Run one eval baseline system over an image dir -> preds dict.

Systems A-D live in ptl.eval.baselines with three result shapes: A
returns a doc dict, B a (doc, conf) tuple, C/D a per-crop list whose
rejected entries carry no doc. This module normalises them into one
{pred_id: doc} mapping plus a summary, so `ptl baseline` output feeds
`ptl eval` directly. Extra pred ids (multi-crop 'stem#i') are ignored
by the scorer unless labels match them.
"""
import os

from ptl.eval.baselines import a_tesseract, b_spark_raw, c_full_spark
from ptl.eval.baselines import d_full_glimmer

SYSTEMS = {"a": a_tesseract.run, "b": b_spark_raw.run,
           "c": c_full_spark.run, "d": d_full_glimmer.run}

IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png"})


def _as_docs(result):
    """Normalise one baseline result to [(crop_index|None, doc)]."""
    if isinstance(result, tuple):
        return [(None, result[0])]
    if isinstance(result, dict):
        return [(None, result)]
    if isinstance(result, list):
        return [(r.get("crop"), r["doc"]) for r in result if "doc" in r]
    raise TypeError(f"unknown baseline result shape: {type(result)!r}")


def run_baseline(system, images_dir):
    """Run system over sorted images; return (preds, summary).

    A lone accepted doc keys by image stem; several key as stem#crop.
    Images with no accepted doc land in summary['missing']; per-image
    errors are collected (never abort the batch) in summary['errors'].
    """
    if system not in SYSTEMS:
        raise ValueError(f"unknown system {system!r}; want one of "
                         f"{sorted(SYSTEMS)}")
    run = SYSTEMS[system]
    names = sorted(n for n in os.listdir(images_dir)
                   if not n.startswith(".")
                   and os.path.splitext(n)[1].lower() in IMAGE_EXTS)
    preds, missing, errors = {}, [], {}
    for name in names:
        stem = os.path.splitext(name)[0]
        try:
            docs = _as_docs(run(os.path.join(images_dir, name)))
        except Exception as e:  # noqa: BLE001 - one bad image must not
            errors[stem] = f"{type(e).__name__}: {e}"  # kill a 150-batch
            continue
        if not docs:
            missing.append(stem)
        elif len(docs) == 1:
            preds[stem] = docs[0][1]
        else:
            for index, doc in docs:
                preds[f"{stem}#{index}"] = doc
    summary = {"system": system, "images": len(names),
               "preds": len(preds), "missing": missing, "errors": errors}
    return preds, summary
