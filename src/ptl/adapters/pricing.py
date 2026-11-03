"""Pay-as-you-go cost estimates for external model calls.

Rates are copied from the official pricing page (fetched 2026-11-02):
https://dev.meta.ai/docs/pricing-rate-limits

- Muse Spark standard: $1.25 / 1M input tokens, $4.25 / 1M output tokens
  (cached input $0.15 / 1M is NOT applied: our usage blocks do not split
  cached input, so estimates are a slight upper bound for cached traffic).
- Muse Spark contributor: $0.10 / 1M input, $0.20 / 1M output.
- SAM 3.1: $2.50 / 1k images segmented ($0.20 / 1k video frames; not used
  here since the pipeline only segments still images: one call = one image).
- Local engines (muse-glimmer default, tesseract): billed $0.

Unknown models return None: an estimate is only shown when every leg of a
run is priced, so a displayed total is never silently partial.

THB figures multiply the USD estimate by a pinned mid-market rate
(USD_THB, with its date below), rounded to 2 decimals: close enough
for a ~2-cent receipt, and re-pinnable when the rate drifts.
"""

SPARK_STD_INPUT_PER_1M = 1.25
SPARK_STD_OUTPUT_PER_1M = 4.25
SPARK_CONTRIB_INPUT_PER_1M = 0.10
SPARK_CONTRIB_OUTPUT_PER_1M = 0.20
SAM_PER_IMAGE = 2.50 / 1000

LOCAL_MODELS = frozenset({"muse-glimmer", "tesseract"})

# Mid-market consensus 2026-11-01 (33.56-33.75 across converter
# desks that day): pinned, not live. Re-pin when visibly stale.
USD_THB = 33.65
USD_THB_AS_OF = "2026-11-01"


def estimate_usd(model, stats):
    """Estimate USD for one adapter's stats block, or None if unpriced."""
    if not model or not stats:
        return None
    name = model.lower()
    if name in LOCAL_MODELS:
        return 0.0
    if name.endswith("-contributor") and "spark" in name:
        in_1m, out_1m = SPARK_CONTRIB_INPUT_PER_1M, SPARK_CONTRIB_OUTPUT_PER_1M
    elif "spark" in name:
        in_1m, out_1m = SPARK_STD_INPUT_PER_1M, SPARK_STD_OUTPUT_PER_1M
    elif name.startswith("sam-"):
        return round(stats.get("calls", 0) * SAM_PER_IMAGE, 6)
    else:
        return None
    cost = stats.get("input_tokens", 0) / 1e6 * in_1m
    cost += stats.get("output_tokens", 0) / 1e6 * out_1m
    return round(cost, 6)


def usd_to_thb(usd):
    """Convert a USD estimate to THB, or None when unpriced."""
    if usd is None:
        return None
    return round(usd * USD_THB, 2)
