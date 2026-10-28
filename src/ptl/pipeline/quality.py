"""Per-crop quality gate: blur/contrast/skew -> accept or reject-reprompt."""
from dataclasses import dataclass

BLUR_MIN = 0.15      # Laplacian-variance normalised; below = too blurry
CONTRAST_MIN = 0.10  # RMS contrast normalised; below = too flat
SKEW_MAX_DEG = 8.0   # residual skew after deskew


@dataclass
class GateResult:
    passed: bool
    reasons: list

    def to_dict(self):
        return {"passed_gate": self.passed, "reasons": self.reasons}


def quality_gate(blur, contrast, skew_deg):
    reasons = []
    if blur is not None and blur < BLUR_MIN:
        reasons.append(f"blur {blur:.3f} < {BLUR_MIN}")
    if contrast is not None and contrast < CONTRAST_MIN:
        reasons.append(f"contrast {contrast:.3f} < {CONTRAST_MIN}")
    if skew_deg is not None and abs(skew_deg) > SKEW_MAX_DEG:
        reasons.append(f"skew {skew_deg:.1f}deg > {SKEW_MAX_DEG}deg")
    return GateResult(passed=not reasons, reasons=reasons)
