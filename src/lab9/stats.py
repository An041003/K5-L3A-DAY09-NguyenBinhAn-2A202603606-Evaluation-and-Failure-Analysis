"""Calibrated classification metrics and paired uncertainty for Lab 9.

FAIL is positive: the evaluator's job is to detect errors.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

POS = "FAIL"


def _validate_labels(human: Sequence[str], judge: Sequence[str]) -> None:
    if len(human) != len(judge) or not human:
        raise ValueError("human and judge must be non-empty, equally sized sequences")
    if any(x not in {"PASS", "FAIL"} for x in (*human, *judge)):
        raise ValueError("labels must be PASS or FAIL")


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    _validate_labels(human, judge)
    return {
        "tp": sum(h == POS and j == POS for h, j in zip(human, judge)),
        "fp": sum(h != POS and j == POS for h, j in zip(human, judge)),
        "fn": sum(h == POS and j != POS for h, j in zip(human, judge)),
        "tn": sum(h != POS and j != POS for h, j in zip(human, judge)),
    }


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    c = confusion(human, judge)
    p = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else 0.0
    r = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else 0.0
    return p, r


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    c = confusion(human, judge)
    n = sum(c.values())
    po = (c["tp"] + c["tn"]) / n
    p_h_pos = (c["tp"] + c["fn"]) / n
    p_j_pos = (c["tp"] + c["fp"]) / n
    pe = p_h_pos * p_j_pos + (1 - p_h_pos) * (1 - p_j_pos)
    if math.isclose(pe, 1.0, abs_tol=1e-14):
        raise ValueError("kappa is undefined: expected agreement is 1")
    return (po - pe) / (1 - pe)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    if any(not math.isfinite(x) or x < 0 or x > 1 for x in (observed_rate, sensitivity, specificity)):
        raise ValueError("rates must be finite values within [0, 1]")
    denom = sensitivity + specificity - 1
    if denom <= 0:
        raise ValueError("judge is not informative: sensitivity + specificity <= 1")
    return min(1.0, max(0.0, (observed_rate + specificity - 1) / denom))


def paired_bootstrap(
    a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
    rng: int = 2027, confidence: float = 0.95,
) -> tuple[float, float, float]:
    """Percentile bootstrap of paired per-item means, *not* individual trials."""
    import numpy as np
    from scipy.stats import bootstrap

    x, y = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if not len(x) or x.shape != y.shape or x.ndim != 1:
        raise ValueError("paired vectors must be non-empty 1-D arrays of equal length")
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("bootstrap samples must be finite")
    if not isinstance(n_resamples, int) or n_resamples <= 0 or not 0 < confidence < 1:
        raise ValueError("invalid bootstrap settings")
    diffs = x - y
    point = float(np.mean(diffs))
    if np.all(diffs == 0):
        return 0.0, 0.0, 0.0
    result = bootstrap(
        (x, y), lambda left, right, axis: np.mean(left - right, axis=axis),
        paired=True, n_resamples=n_resamples, method="percentile",
        confidence_level=confidence, rng=np.random.default_rng(rng), vectorized=True,
    )
    return point, float(result.confidence_interval.low), float(result.confidence_interval.high)


def _validate_pass_args(n: int, c: int, k: int) -> None:
    if any(type(v) is not int for v in (n, c, k)) or n < 1 or not 0 <= c <= n or not 1 <= k <= n:
        raise ValueError("require integer n>=1, 0<=c<=n, and 1<=k<=n")


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability at least one success among k draws without replacement."""
    _validate_pass_args(n, c, k)
    return 1.0 - (math.comb(n - c, k) / math.comb(n, k) if n - c >= k else 0.0)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """Probability all k draws succeed (pass^k reliability estimate)."""
    _validate_pass_args(n, c, k)
    return math.comb(c, k) / math.comb(n, k) if c >= k else 0.0
