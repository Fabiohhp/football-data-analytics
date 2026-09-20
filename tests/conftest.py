"""Shared test setup.

Every test runs against the synthetic fixture, never the real snapshot, so the
suite passes on a fresh clone with Part 1's database switched off.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "gold"

sys.path.insert(0, str(REPO_ROOT / "src"))


@pytest.fixture(autouse=True)
def _point_at_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make `snapshot.open_snapshot()` find the fixture by default."""
    monkeypatch.setenv("GOLD_SNAPSHOT_DIR", str(FIXTURE_DIR))


@pytest.fixture
def snap():
    """The fixture snapshot, opened once per test."""
    from football_analytics import snapshot

    return snapshot.open_snapshot()
