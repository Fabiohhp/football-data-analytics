"""Uncertainty, defined once.

CLAUDE.md §7 asks every estimate a conclusion rests on to carry an interval, and
§7 also asks notebooks to be reproducible with their outputs committed. Those two
pull against each other: a bootstrap is random, so an unseeded one rewrites its
own answer on every run and makes the committed notebook a moving target.

Everything here therefore takes a **default seed**. The numbers are stable across
runs and machines, and a reader who wants to see the sampling noise can pass a
different one.

The helpers are deliberately small and answer three questions:

* :func:`correlation_ci` — how strong is this relationship, and how sure are we?
* :func:`paired_correlation_difference_ci` — is predictor A *better* than
  predictor B at explaining the same outcome? Resampling the same rows for both
  is the point: the two correlations share their sample, so comparing their
  separate intervals would overstate the uncertainty in the difference.
* :func:`mean_difference_ci` — did this group really move?
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

DEFAULT_RESAMPLES = 10_000
DEFAULT_SEED = 20260920
DEFAULT_CONFIDENCE = 0.95


@dataclass(frozen=True)
class Estimate:
    """A point estimate with a bootstrap interval, and how it was produced."""

    value: float
    low: float
    high: float
    n: int
    resamples: int
    confidence: float
    p_value: float | None = None

    @property
    def excludes_zero(self) -> bool:
        """Whether the whole interval sits on one side of zero."""
        return self.low > 0.0 or self.high < 0.0

    def __str__(self) -> str:
        pct = round(self.confidence * 100)
        text = f"{self.value:+.3f} ({pct}% CI {self.low:+.3f} to {self.high:+.3f}, n = {self.n:,})"
        if self.p_value is not None:
            text += f", p = {self.p_value:.3f}"
        return text


def _percentiles(confidence: float) -> tuple[float, float]:
    tail = (1.0 - confidence) / 2.0
    return 100.0 * tail, 100.0 * (1.0 - tail)


def _as_array(values) -> np.ndarray:
    return np.asarray(values, dtype=float)


# Resampling happens in blocks rather than as one big array. 10,000 resamples of a
# 1,000-row sample is ten million floats per variable, and the paired difference
# needs three of those at once; blocking holds the peak allocation to a few MB
# whatever the sample size, at no measurable cost in speed.
_BLOCK = 1_000


def _bootstrap_blocks(n: int, resamples: int, seed: int):
    """Yield resample index blocks, so nothing allocates the whole draw at once."""
    rng = np.random.default_rng(seed)
    remaining = resamples
    while remaining > 0:
        size = min(_BLOCK, remaining)
        yield rng.integers(0, n, size=(size, n))
        remaining -= size


def _pearson_rows(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Pearson r for every row of two (resamples, n) arrays at once.

    Calling `scipy.stats.pearsonr` in a Python loop over 10,000 resamples costs a
    couple of seconds per estimate — enough to slow the test suite and every
    notebook CI executes. The closed form over centred rows is the same number and
    about two orders of magnitude faster.
    """
    xm = x - x.mean(axis=1, keepdims=True)
    ym = y - y.mean(axis=1, keepdims=True)
    numerator = (xm * ym).sum(axis=1)
    denominator = np.sqrt((xm * xm).sum(axis=1) * (ym * ym).sum(axis=1))
    # A resample can draw one club 300 times over, leaving zero variance and a 0/0.
    # Those resamples carry no information about the correlation, so they are
    # dropped by the nan-aware percentile rather than poisoning the interval.
    with np.errstate(invalid="ignore", divide="ignore"):
        return numerator / denominator


def correlation_ci(
    x,
    y,
    *,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
    confidence: float = DEFAULT_CONFIDENCE,
) -> Estimate:
    """Pearson correlation with a bootstrap interval over resampled pairs.

    Pairs are resampled together, so the interval reflects uncertainty about which
    clubs or players happened to be in the sample — which is the question an
    interval on a correlation should answer here.
    """
    x, y = _as_array(x), _as_array(y)
    if x.shape != y.shape:
        raise ValueError(f"x and y must be the same length, got {x.shape} and {y.shape}")

    result = stats.pearsonr(x, y)
    boots = np.concatenate(
        [_pearson_rows(x[idx], y[idx]) for idx in _bootstrap_blocks(len(x), resamples, seed)]
    )
    low, high = np.nanpercentile(boots, _percentiles(confidence))
    return Estimate(
        value=float(result.statistic),
        low=float(low),
        high=float(high),
        n=len(x),
        resamples=resamples,
        confidence=confidence,
        p_value=float(result.pvalue),
    )


def paired_correlation_difference_ci(
    a,
    b,
    target,
    *,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
    confidence: float = DEFAULT_CONFIDENCE,
) -> Estimate:
    """Is `a` more strongly correlated with `target` than `b` is?

    Returns ``corr(a, target) - corr(b, target)``, bootstrapped by resampling rows
    and recomputing **both** correlations on the same resample. Comparing two
    independently-bootstrapped intervals instead would treat the shared sample as
    two separate ones and hide the fact that the two correlations move together.

    An interval that includes zero means the two predictors are not
    distinguishable on this sample — which is a finding, not a failure.
    """
    a, b, target = _as_array(a), _as_array(b), _as_array(target)
    if not (a.shape == b.shape == target.shape):
        raise ValueError("a, b and target must all be the same length")

    observed = stats.pearsonr(a, target).statistic - stats.pearsonr(b, target).statistic
    boots = np.concatenate(
        [
            _pearson_rows(a[idx], target[idx]) - _pearson_rows(b[idx], target[idx])
            for idx in _bootstrap_blocks(len(a), resamples, seed)
        ]
    )
    low, high = np.nanpercentile(boots, _percentiles(confidence))
    return Estimate(
        value=float(observed),
        low=float(low),
        high=float(high),
        n=len(a),
        resamples=resamples,
        confidence=confidence,
    )


def mean_ci(
    values,
    *,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
    confidence: float = DEFAULT_CONFIDENCE,
) -> Estimate:
    """The mean, with a bootstrap interval."""
    values = _as_array(values)
    boots = np.concatenate(
        [values[idx].mean(axis=1) for idx in _bootstrap_blocks(len(values), resamples, seed)]
    )
    low, high = np.percentile(boots, _percentiles(confidence))
    return Estimate(
        value=float(values.mean()),
        low=float(low),
        high=float(high),
        n=len(values),
        resamples=resamples,
        confidence=confidence,
    )


def mean_difference_ci(
    before,
    after,
    *,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
    confidence: float = DEFAULT_CONFIDENCE,
) -> Estimate:
    """``mean(after) - mean(before)`` for paired observations, bootstrapped.

    Paired: the two arrays describe the same clubs or players in two periods, so
    rows are resampled together and the difference is computed within the
    resample. This is the right shape for "did the overperformers fall back?".
    """
    before, after = _as_array(before), _as_array(after)
    if before.shape != after.shape:
        raise ValueError("before and after must be the same length")

    boots = np.concatenate(
        [
            after[idx].mean(axis=1) - before[idx].mean(axis=1)
            for idx in _bootstrap_blocks(len(before), resamples, seed)
        ]
    )
    low, high = np.percentile(boots, _percentiles(confidence))
    return Estimate(
        value=float(after.mean() - before.mean()),
        low=float(low),
        high=float(high),
        n=len(before),
        resamples=resamples,
        confidence=confidence,
    )
