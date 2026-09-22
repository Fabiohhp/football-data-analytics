"""The uncertainty helpers.

The properties that matter are not "does scipy compute a correlation" but the two
things these wrappers are for: **the same seed gives the same answer**, because a
notebook's committed outputs must be reproducible (CLAUDE.md §7), and **the paired
difference is genuinely paired**, because that is the one calculation here a
reader could not do in their head.
"""

from __future__ import annotations

import numpy as np
import pytest

from football_analytics import stats as st


@pytest.fixture
def correlated():
    rng = np.random.default_rng(11)
    x = rng.normal(size=300)
    y = 0.6 * x + rng.normal(size=300)
    return x, y


class TestReproducibility:
    def test_same_seed_gives_identical_intervals(self, correlated):
        x, y = correlated
        first = st.correlation_ci(x, y)
        second = st.correlation_ci(x, y)
        assert (first.low, first.high) == (second.low, second.high)

    def test_a_different_seed_moves_the_interval_but_not_the_estimate(self, correlated):
        x, y = correlated
        default = st.correlation_ci(x, y)
        other = st.correlation_ci(x, y, seed=99)
        assert default.value == other.value, "the point estimate is not random"
        assert (default.low, default.high) != (other.low, other.high)

    def test_the_default_seed_is_pinned(self):
        # If this number ever changes, every committed notebook output changes with
        # it. That should be a deliberate act, not a side effect.
        assert st.DEFAULT_SEED == 20260920


class TestVectorisedPearson:
    """The fast path has to agree with scipy, or every interval here is fiction."""

    def test_matches_scipy_row_for_row(self):
        from scipy import stats as scipy_stats

        rng = np.random.default_rng(21)
        x = rng.normal(size=(50, 120))
        y = 0.4 * x + rng.normal(size=(50, 120))

        fast = st._pearson_rows(x, y)
        slow = np.array(
            [scipy_stats.pearsonr(xi, yi).statistic for xi, yi in zip(x, y, strict=True)]
        )

        assert fast == pytest.approx(slow, abs=1e-12)

    def test_a_zero_variance_resample_becomes_nan_rather_than_an_error(self):
        # A resample can draw the same club every time. That row says nothing about
        # the correlation and must not raise or silently become a number.
        flat = np.ones((1, 10))
        varied = np.arange(10, dtype=float).reshape(1, 10)
        assert np.isnan(st._pearson_rows(flat, varied)).all()

    def test_blocks_cover_exactly_the_requested_resamples(self):
        blocks = list(st._bootstrap_blocks(n=7, resamples=2_500, seed=1))
        assert sum(len(b) for b in blocks) == 2_500
        assert all(b.shape[1] == 7 for b in blocks)
        assert all(0 <= b.min() and b.max() < 7 for b in blocks)


class TestCorrelationCi:
    def test_interval_brackets_the_estimate(self, correlated):
        x, y = correlated
        est = st.correlation_ci(x, y)
        assert est.low < est.value < est.high

    def test_a_real_relationship_excludes_zero(self, correlated):
        x, y = correlated
        assert st.correlation_ci(x, y).excludes_zero

    def test_pure_noise_does_not_exclude_zero(self):
        rng = np.random.default_rng(3)
        est = st.correlation_ci(rng.normal(size=400), rng.normal(size=400))
        assert not est.excludes_zero

    def test_confidence_widens_the_interval(self, correlated):
        x, y = correlated
        narrow = st.correlation_ci(x, y, confidence=0.80)
        wide = st.correlation_ci(x, y, confidence=0.99)
        assert wide.high - wide.low > narrow.high - narrow.low

    def test_mismatched_lengths_are_rejected(self):
        with pytest.raises(ValueError, match="same length"):
            st.correlation_ci([1, 2, 3], [1, 2])


class TestPairedCorrelationDifference:
    def test_the_better_predictor_wins_and_the_interval_excludes_zero(self):
        rng = np.random.default_rng(5)
        target = rng.normal(size=400)
        good = target + rng.normal(scale=0.4, size=400)
        poor = target + rng.normal(scale=3.0, size=400)

        est = st.paired_correlation_difference_ci(good, poor, target)
        assert est.value > 0
        assert est.excludes_zero

    def test_two_equally_good_predictors_are_not_distinguishable(self):
        rng = np.random.default_rng(6)
        target = rng.normal(size=400)
        a = target + rng.normal(scale=1.0, size=400)
        b = target + rng.normal(scale=1.0, size=400)

        assert not st.paired_correlation_difference_ci(a, b, target).excludes_zero

    def test_pairing_is_tighter_than_comparing_separate_intervals(self):
        """The reason this helper exists rather than two `correlation_ci` calls.

        Both correlations are computed on the same rows, so they rise and fall
        together and the difference is pinned down better than either correlation
        is. Differencing two independent intervals would be wider — and would call
        a real difference inconclusive.
        """
        rng = np.random.default_rng(8)
        target = rng.normal(size=300)
        a = target + rng.normal(scale=0.8, size=300)
        b = target + rng.normal(scale=1.2, size=300)

        paired = st.paired_correlation_difference_ci(a, b, target)
        ci_a = st.correlation_ci(a, target)
        ci_b = st.correlation_ci(b, target)
        naive_width = (ci_a.high - ci_b.low) - (ci_a.low - ci_b.high)

        assert paired.high - paired.low < naive_width

    def test_mismatched_lengths_are_rejected(self):
        with pytest.raises(ValueError, match="same length"):
            st.paired_correlation_difference_ci([1, 2, 3], [1, 2, 3], [1, 2])


class TestMeans:
    def test_mean_ci_brackets_the_mean(self):
        rng = np.random.default_rng(12)
        values = rng.normal(loc=5.0, scale=2.0, size=500)
        est = st.mean_ci(values)
        assert est.low < est.value < est.high
        assert est.value == pytest.approx(values.mean())

    def test_mean_difference_detects_a_real_shift(self):
        rng = np.random.default_rng(13)
        before = rng.normal(loc=6.0, size=300)
        after = before - 4.0 + rng.normal(scale=0.5, size=300)

        est = st.mean_difference_ci(before, after)
        assert est.value == pytest.approx(-4.0, abs=0.2)
        assert est.excludes_zero

    def test_mean_difference_rejects_unpaired_input(self):
        with pytest.raises(ValueError, match="same length"):
            st.mean_difference_ci([1, 2, 3], [1, 2])


class TestEstimateFormatting:
    def test_str_states_the_interval_and_the_sample_size(self):
        est = st.Estimate(
            value=0.5, low=0.1, high=0.9, n=1234, resamples=10, confidence=0.95, p_value=0.01
        )
        text = str(est)
        assert "+0.500" in text
        assert "95% CI" in text
        assert "1,234" in text
        assert "p = 0.010" in text
