"""Chart helpers: the coordinate conversion is the part that must not be wrong.

A mis-scaled pitch draws a shot map that looks plausible and is backwards, so
the conversion and the penalty-spot landmark are pinned down here. The styling
functions are checked only for "runs and sets what it claims" — how a chart
looks is a judgement call, not an assertion.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib as mpl  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from football_analytics import viz  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


class TestCoordinateConversion:
    def test_understat_maps_onto_opta(self):
        # Understat normalizes to [0, 1]; Opta is the same system times 100.
        x, y = viz.to_opta(pd.Series([0.0, 0.5, 1.0]), pd.Series([0.0, 0.5, 1.0]))
        assert x.tolist() == [0.0, 50.0, 100.0]
        assert y.tolist() == [0.0, 50.0, 100.0]

    def test_the_penalty_spot_lands_on_optas_own_spot(self):
        """The whole orientation check rests on this equality."""
        x, y = viz.to_opta(0.885, 0.5)
        assert (x, y) == pytest.approx(viz.PENALTY_SPOT_OPTA)

    def test_scalars_work_too(self):
        assert viz.to_opta(0.885, 0.5) == pytest.approx((88.5, 50.0))


class TestStyle:
    def test_apply_style_sets_an_opaque_light_surface(self):
        # A transparent background would vanish against GitHub's dark theme.
        viz.apply_style()
        assert mpl.rcParams["figure.facecolor"] == viz.SURFACE
        assert mpl.rcParams["savefig.facecolor"] == viz.SURFACE
        assert mpl.rcParams["axes.spines.top"] is False

    def test_title_block_sets_a_left_aligned_title(self):
        viz.apply_style()
        _, ax = plt.subplots()
        viz.title_block(ax, "A title", "a subtitle")
        # The style sets axes.titlelocation to "left", so the centre title —
        # which is what get_title() returns by default — stays empty.
        assert ax.get_title(loc="left") == "A title"
        assert ax.get_title() == ""
        assert any("a subtitle" == t.get_text() for t in ax.texts)

    def test_annotate_source_writes_the_citation_onto_the_figure(self):
        viz.apply_style()
        fig, ax = plt.subplots()
        viz.annotate_source(ax, "matches 2024-08-15 to 2026-09-19")
        assert any("2024-08-15" in t.get_text() for t in fig.texts)


def shots_frame(results: list[str]) -> pd.DataFrame:
    n = len(results)
    return pd.DataFrame(
        {
            "x": [0.885] * n,
            "y": [0.5] * n,
            "xg": [0.76] * n,
            "result": results,
        }
    )


class TestShotMap:
    def test_draws_shots_and_goals(self):
        viz.apply_style()
        fig, ax = viz.shot_map(shots_frame(["Goal", "SavedShot", "MissedShots"]))
        labels = [t.get_text() for t in ax.get_legend().get_texts()]
        assert labels == ["Shot", "Goal"]
        assert fig.get_facecolor() is not None

    @pytest.mark.parametrize(
        "results",
        [["Goal", "Goal"], ["SavedShot", "BlockedShot"]],
        ids=["all-goals", "no-goals"],
    )
    def test_survives_a_single_category(self, results):
        # A player with only goals, or a team with none, must still plot.
        viz.apply_style()
        _, ax = viz.shot_map(shots_frame(results))
        assert ax is not None

    def test_null_xg_does_not_break_marker_sizing(self):
        viz.apply_style()
        frame = shots_frame(["Goal", "SavedShot"])
        frame.loc[0, "xg"] = None
        _, ax = viz.shot_map(frame)
        assert ax is not None

    def test_penalty_spot_overlay_is_optional(self):
        viz.apply_style()
        _, plain = viz.shot_map(shots_frame(["Goal"]))
        _, ringed = viz.shot_map(shots_frame(["Goal"]), show_penalty_spot=True)
        # The ring is two extra collections: the halo and the dashed circle.
        assert len(ringed.collections) == len(plain.collections) + 2


class TestHalfPitch:
    def test_returns_a_pitch_object_for_further_plotting(self):
        viz.apply_style()
        fig, ax, pitch = viz.half_pitch()
        assert hasattr(pitch, "scatter")
        assert fig is not None and ax is not None

    def test_crop_changes_the_visible_area(self):
        viz.apply_style()
        _, cropped, _ = viz.half_pitch(crop=-20.0)
        _, full, _ = viz.half_pitch(crop=0.0)
        assert cropped.get_ylim() != full.get_ylim()
