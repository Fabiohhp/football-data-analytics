"""Build the tiny synthetic Gold snapshot that CI runs on.

    uv run python tests/fixtures/make_gold_fixture.py

CI has no access to Part 1's warehouse, and the real snapshot is gitignored
until CLAUDE.md §13 decides what may be published. So this writes a handful of
rows per Gold table, in the *exact* column types the contract records, and the
whole pipeline is pointed at it with ``GOLD_SNAPSHOT_DIR``.

Rows are built by column *name*, never by position. Physical column order in
Gold is not meaningful and not stable — ``dim_stadiums.address`` sits after
``loaded_at`` because Part 1 added it with ``ALTER TABLE ADD COLUMN`` to a
warehouse that predated it. Positional rows would quietly shift a value into
the neighbouring column, which is the exact class of bug the contract exists to
catch, so the generator refuses to play that game.

The data is invented, but the *shape* is not. Every trap in CLAUDE.md §5 is
deliberately present, so a model or notebook that falls into one fails here
rather than in production:

* an ``Unknown`` member at key 0 in every dimension (trap 3), and a match that
  reports no referee;
* one player with two SCD Type 2 versions after a January transfer, so grouping
  by ``player_key`` instead of ``understat_player_id`` splits their season
  (traps 1 and 2);
* rows with a NULL ``match_key`` in both event facts (trap 4);
* an ``AWARDED`` match — really played, real score, real xG — inside a *completed*
  season, so a model that filters on ``status = 'FINISHED'`` alone leaves two
  clubs a match short and fails the fixture-list assertion (trap 6);
* a ``POSTPONED`` match carrying a phantom 0-0 with ``result = 'DRAW'`` and no xG,
  which both of ``int_team_matches``' filters must exclude (trap 6);
* a ``SCHEDULED`` match whose scores are NULL — absent from the real snapshot,
  because Part 1 loads only up to the current date, but permitted by Gold and
  scored as a 0-0 draw by anything that lets it through (trap 6);
* one fixture split across two rows (trap 13), also inside the completed season.
  **Both halves are ``FINISHED`` and both carry the same scoreline** — measured
  against the real snapshot, where all eleven comparable pairs agree — so only the
  missing ``football_data_match_id`` separates them. The half with no xG is the
  Football-Data one, which is also how trap 7 appears in reality: every counting
  match without xG is the Football-Data half of a split fixture;
* a pair of duplicated shots under different shot ids (trap 14);
* penalties sitting on exactly x=0.885, y=0.5 at 0.76 xG (trap 10), placed by a
  counter rather than a probability so they cannot fall out of the fixture when an
  unrelated change shifts the random stream;
* every value of ``result``, ``situation`` and ``shot_type`` the real snapshot
  holds (trap 11), including the plural ``MissedShots`` and an ``OwnGoal`` — which
  is a *shot result*, sitting on the team of the player who scored it;
* two seasons either side of the August cutoff (trap 5).

Where the real snapshot and this file disagree about a trap's *shape*, the real
snapshot wins: several of the notes above are corrections made after measuring it,
not guesses. A fixture that carried a trap in a form the data does not take would
let a broken model pass CI.
"""

from __future__ import annotations

import json
import random
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from football_analytics import gold  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "gold"
SEED = 20260920
LOADED_AT = "2026-09-20T12:00:00+00:00"

# PostgreSQL contract type -> the DuckDB type to cast the fixture column to, so
# the fixture's Parquet schema matches a real export's column for column.
TYPE_MAP = {
    "bigint": "BIGINT",
    "integer": "INTEGER",
    "smallint": "SMALLINT",
    "text": "VARCHAR",
    "date": "DATE",
    "boolean": "BOOLEAN",
    "timestamptz": "TIMESTAMPTZ",
}


def duckdb_type(contract_type: str) -> str:
    """Map a contract type string onto a DuckDB type."""
    if contract_type.startswith("numeric("):
        return contract_type.replace("numeric", "DECIMAL").upper()
    if contract_type.startswith("varchar"):
        return "VARCHAR"
    return TYPE_MAP[contract_type]


def named(header: tuple[str, ...], rows: list[tuple]) -> list[dict[str, Any]]:
    """Zip a readable literal table into dicts keyed by column name."""
    return [dict(zip(header, row, strict=True)) for row in rows]


# --- the invented world ----------------------------------------------------

TEAMS = named(
    (
        "team_key",
        "canonical_name",
        "football_data_name",
        "understat_name",
        "football_data_id",
        "understat_id",
    ),
    [
        (0, "Unknown", None, None, None, None),
        (1, "Arsenal", "Arsenal FC", "Arsenal", 57, 83),
        (2, "Liverpool", "Liverpool FC", "Liverpool", 64, 87),
        (3, "Chelsea", "Chelsea FC", "Chelsea", 61, 80),
        (4, "Everton", "Everton FC", "Everton", 62, 72),
        (5, "Barcelona", "FC Barcelona", "Barcelona", 81, 71),
        (6, "Real Madrid", "Real Madrid CF", "Real Madrid", 86, 76),
    ],
)

PL_TEAMS = [1, 2, 3, 4]
PD_TEAMS = [5, 6]
HOME_STADIUM = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6}

# `city` and `capacity` stay NULL: Gold has no source for them (trap 9).
STADIUMS = named(
    ("stadium_key", "stadium_name", "address", "country"),
    [
        (0, "Unknown", None, None),
        (1, "Emirates Stadium", "Hornsey Rd, London N7 7AJ", "England"),
        (2, "Anfield", "Anfield Rd, Liverpool L4 0TH", "England"),
        (3, "Stamford Bridge", "Fulham Rd, London SW6 1HS", "England"),
        (4, "Goodison Park", "Goodison Rd, Liverpool L4 4EL", "England"),
        (5, "Spotify Camp Nou", "C. d'Aristides Maillol, Barcelona", "Spain"),
        (6, "Estadio Santiago Bernabeu", "Av. de Concha Espina 1, Madrid", "Spain"),
    ],
)

REFEREES = named(
    ("referee_key", "football_data_id", "referee_name", "nationality"),
    [
        (0, None, "Unknown", None),
        (1, 11001, "Michael Oliver", "England"),
        (2, 11002, "Anthony Taylor", "England"),
        (3, 11003, "Jesus Gil Manzano", "Spain"),
    ],
)

# understat_player_id 103 appears twice: a January move from Chelsea to Arsenal.
# Grouping that player's season by player_key splits it in two (trap 1).
PLAYERS = named(
    (
        "player_key",
        "understat_player_id",
        "player_name",
        "position",
        "current_team_key",
        "valid_from",
        "valid_to",
        "is_current",
    ),
    [
        (0, 0, "Unknown", None, None, date(1900, 1, 1), None, True),
        (1, 101, "Bukayo Saka", "F M S", 1, date(2024, 8, 16), None, True),
        (2, 102, "Mohamed Salah", "F M S", 2, date(2024, 8, 17), None, True),
        (3, 103, "Cole Palmer", "AM L", 3, date(2024, 8, 17), date(2025, 1, 31), False),
        (4, 103, "Cole Palmer", "AM L", 1, date(2025, 2, 1), None, True),
        (5, 105, "Jarrad Branthwaite", "D C", 4, date(2024, 8, 18), None, True),
        (6, 106, "Robert Lewandowski", "F S", 5, date(2024, 8, 18), None, True),
    ],
)

# Squad per club: (player_key, understat_player_id, position).
SQUADS: dict[int, list[tuple[int, int, str]]] = {
    1: [(1, 101, "F M S")],
    2: [(2, 102, "F M S")],
    3: [(3, 103, "AM L")],
    4: [(5, 105, "D C")],
    5: [(6, 106, "F S")],
    6: [],
}
# After the transfer, key 4 is Palmer's current version and he plays for Arsenal.
SQUADS_AFTER_TRANSFER = {**SQUADS, 1: [(1, 101, "F M S"), (4, 103, "AM L")], 3: []}
TRANSFER_DATE = date(2025, 2, 1)

COMPETITION_NAMES = {"PL": "Premier League", "PD": "Primera Division"}


def double_round_robin(teams: list[int]) -> list[tuple[int, int]]:
    """Every ordered pair: each club hosts each other club once."""
    return [(h, a) for h in teams for a in teams if h != a]


def build_matches(rng: random.Random) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Invent a fixture list, and return both the rows and a plan for the facts.

    The plan carries what the event facts need (which clubs, which date, which
    Understat match id), so shots and player events cannot contradict the match
    rows they hang off.
    """
    rows: list[dict[str, Any]] = []
    plan: list[dict[str, Any]] = []
    counters = {"match_key": 0, "fd_id": 500_000, "us_id": 900_000}

    def add(
        *,
        competition_code: str | None,
        season: str,
        matchday: int | None,
        match_date: date,
        home: int,
        away: int,
        status: str = "FINISHED",
        football_data: bool = True,
        scoreline: str | tuple[int, int] = "real",
        with_xg: bool = True,
        referee_key: int = 1,
        competition_name: str | None = None,
    ) -> dict[str, Any]:
        """Add one `fact_matches` row, and return it.

        The three knobs that are *not* the same thing, because the real snapshot
        proves they are not (see the module docstring):

        ``football_data``
            Whether Football-Data knows this fixture, i.e. whether
            ``football_data_match_id`` is set. The Understat half of a split
            fixture is the only row where this is false — and it is `FINISHED`
            and carries a scoreline all the same, which is why this is a separate
            knob from ``status`` and from ``scoreline``.
        ``scoreline``
            ``"real"`` for an invented result, ``"none"`` to leave the goals NULL
            for a fixture that has not been played, ``"phantom"`` for the 0-0
            `DRAW` a POSTPONED match carries although it never kicked off, or an
            explicit ``(home, away)`` pair so the two halves of a split fixture
            agree — in the real snapshot they always do.
        ``with_xg``
            Whether Understat paired the match, i.e. whether there is any xG,
            npxG, PPDA or xPTS, *and* whether player events and shots exist for
            it at all.
        """
        counters["match_key"] += 1
        counters["fd_id"] += 1
        counters["us_id"] += 1

        row: dict[str, Any] = {
            "match_key": counters["match_key"],
            "football_data_match_id": counters["fd_id"] if football_data else None,
            "understat_match_id": counters["us_id"] if with_xg else None,
            "competition_code": competition_code,
            # Populated even where the code is NULL: that is what the Understat
            # halves of split fixtures look like in the real snapshot.
            "competition_name": competition_name or COMPETITION_NAMES.get(competition_code or ""),
            "season": season,
            "matchday": matchday,
            "match_utc": datetime.combine(match_date, datetime.min.time()).replace(
                hour=15, tzinfo=UTC
            ),
            "match_date": match_date,
            "status": status,
            "home_team_key": home,
            "away_team_key": away,
            "referee_key": referee_key,
            "stadium_key": HOME_STADIUM[home],
        }

        if scoreline == "real":
            hg, ag = rng.randint(0, 4), rng.randint(0, 3)
        elif scoreline == "phantom":
            # A POSTPONED match was never played, and still carries a 0-0 that
            # looks entirely plausible (trap 6).
            hg, ag = 0, 0
        elif scoreline == "none":
            hg = ag = None
        else:
            hg, ag = scoreline

        if hg is not None:
            row |= {
                "home_goals": hg,
                "away_goals": ag,
                "result": "HOME_TEAM" if hg > ag else ("AWAY_TEAM" if ag > hg else "DRAW"),
            }
            # Half-time goals come from Football-Data, so the Understat half of a
            # split fixture has none — and neither does a phantom scoreline.
            if football_data and scoreline == "real":
                row |= {
                    "home_goals_ht": rng.randint(0, hg),
                    "away_goals_ht": rng.randint(0, ag),
                }

        if with_xg:
            hxg = round(rng.uniform(0.4, 3.2), 4)
            axg = round(rng.uniform(0.3, 2.6), 4)
            # npxG is at most xG; a penalty is worth roughly 0.76 of it.
            hxpts = round(rng.uniform(0.3, 2.4), 4)
            row |= {
                "home_xg": hxg,
                "away_xg": axg,
                "home_npxg": max(round(hxg - rng.choice([0.0, 0.0, 0.76]), 4), 0.0),
                "away_npxg": max(round(axg - rng.choice([0.0, 0.0, 0.76]), 4), 0.0),
                "home_ppda": round(rng.uniform(6.0, 18.0), 4),
                "away_ppda": round(rng.uniform(6.0, 18.0), 4),
                "home_deep": rng.randint(2, 14),
                "away_deep": rng.randint(2, 14),
                "home_xpts": hxpts,
                "away_xpts": round(3.0 - hxpts - rng.uniform(0.0, 0.4), 4),
            }
            plan.append(
                {
                    "match_key": counters["match_key"],
                    "understat_match_id": counters["us_id"],
                    "match_date": match_date,
                    "home": home,
                    "away": away,
                    "season": season,
                }
            )

        rows.append(row)
        return row

    # --- 2024/25: a full double round robin in the PL, and one in Spain ----
    #
    # This season is *complete*, which is what makes it the right place for the two
    # traps that only a wrong filter exposes. `mart_team_season` asserts that every
    # club in a completed season played twice its number of opponents, so a model
    # that drops the AWARDED match on matchday 7, or keeps the Understat half of the
    # split fixture on matchday 5, fails that assertion here instead of shipping a
    # league table one match short.
    day = date(2024, 8, 17)
    for matchday, (home, away) in enumerate(double_round_robin(PL_TEAMS), start=1):
        match = add(
            competition_code="PL",
            season="2024/25",
            matchday=matchday,
            match_date=day,
            home=home,
            away=away,
            # Matchday 7 was abandoned and then awarded by the federation: really
            # played, real score, real xG, and it counted towards the real league
            # table. `status = 'FINISHED'` alone drops it (trap 6).
            status="AWARDED" if matchday == 7 else "FINISHED",
            # Matchday 5 is the Football-Data half of a fixture the sources dated
            # differently, so its xG sits on the twin added below and is NULL here
            # (traps 7 and 13). In the real snapshot these are the same rows: every
            # counting match with no xG is the Football-Data half of a split fixture.
            with_xg=(matchday != 5),
            referee_key=rng.choice([1, 2]),
        )

        if matchday == 5:
            # The Understat half of that fixture, dated a day later. It carries the
            # xG and the player events, and it is `FINISHED` **with the same
            # scoreline** — measured: all eleven comparable pairs in the real
            # snapshot agree on the score. So `status` does not separate the halves
            # and only the missing `football_data_match_id` does, which is exactly
            # the mistake `int_team_matches` has to not make. `competition_code` and
            # `matchday` are NULL and no official is reported, as in the real rows.
            add(
                competition_code=None,
                competition_name=COMPETITION_NAMES["PL"],
                season="2024/25",
                matchday=None,
                match_date=day + timedelta(days=1),
                home=home,
                away=away,
                football_data=False,
                scoreline=(match["home_goals"], match["away_goals"]),
                with_xg=True,
                referee_key=0,
            )

        day += timedelta(days=21)

    for matchday, (home, away) in enumerate(double_round_robin(PD_TEAMS), start=1):
        add(
            competition_code="PD",
            season="2024/25",
            matchday=matchday,
            match_date=date(2024, 9, 1) + timedelta(days=90 * matchday),
            home=home,
            away=away,
            referee_key=3,
        )

    # --- 2025/26: the new season, just after the August cutoff (trap 5) ----
    add(
        competition_code="PL",
        season="2025/26",
        matchday=1,
        match_date=date(2025, 8, 16),
        home=2,
        away=1,
        referee_key=2,
    )
    # Not played yet, so the scores are NULL. The real snapshot has no such row —
    # Part 1 only loads up to the current date — but Gold permits one, and a model
    # that let it through would score it as a 0-0 draw. Kept so that stays tested.
    add(
        competition_code="PL",
        season="2025/26",
        matchday=2,
        match_date=date(2025, 8, 23),
        home=3,
        away=4,
        status="SCHEDULED",
        scoreline="none",
        with_xg=False,
        referee_key=1,
    )
    # POSTPONED: never played, and the opposite problem. It carries a phantom 0-0
    # with `result = 'DRAW'` and no xG — a scoreline that looks entirely plausible
    # and is entirely fictional (trap 6). It is also the one row left pointing at
    # the Unknown referee (trap 3). Both of int_team_matches' filters must exclude
    # it, and the status filter is the one that does.
    add(
        competition_code="PL",
        season="2025/26",
        matchday=3,
        match_date=date(2025, 8, 30),
        home=4,
        away=3,
        status="POSTPONED",
        scoreline="phantom",
        with_xg=False,
        referee_key=0,
    )
    return rows, plan


def squad_for(team: int, match_date: date) -> list[tuple[int, int, str]]:
    """The club's players as of a date, respecting the January transfer."""
    table = SQUADS_AFTER_TRANSFER if match_date >= TRANSFER_DATE else SQUADS
    return table[team]


def build_events_and_shots(
    rng: random.Random, plan: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Invent player events and shots consistent with the match plan."""
    events: list[dict[str, Any]] = []
    shots: list[dict[str, Any]] = []
    shot_id = 7_000_000
    # Every eleventh shot is a penalty. Deliberately a counter rather than a
    # probability: an 8% chance produced *no* penalty at all on some seeds, which
    # quietly took trap 10 out of the fixture — the thing the fixture exists to
    # guarantee. Counting makes the penalty spot present by construction, and keeps
    # the count stable when an unrelated change shifts the random stream.
    shot_ordinal = 0

    for entry in plan:
        for team, is_home in ((entry["home"], True), (entry["away"], False)):
            for player_key, us_player_id, position in squad_for(team, entry["match_date"]):
                n_shots = rng.randint(0, 4)
                goals = sum(1 for _ in range(n_shots) if rng.random() < 0.22)
                xg_total = 0.0
                scored_left = goals

                for _ in range(n_shots):
                    shot_id += 1
                    shot_ordinal += 1
                    if shot_ordinal % 11 == 0:
                        # Penalties sit on exactly one point of the pitch, at
                        # x=0.885, y=0.5 with zero variance on both axes, averaging
                        # 0.756 xG. That is what confirms the coordinates' meaning
                        # and orientation (trap 10), so the fixture reproduces it
                        # exactly rather than approximately.
                        x, y, xg = 0.885, 0.5, 0.7600
                        situation, shot_type = "Penalty", "RightFoot"
                    else:
                        x = round(rng.uniform(0.74, 0.98), 4)
                        y = round(rng.uniform(0.25, 0.75), 4)
                        xg = round(rng.uniform(0.01, 0.55), 4)
                        situation = rng.choice(
                            ["OpenPlay", "OpenPlay", "FromCorner", "SetPiece", "DirectFreekick"]
                        )
                        shot_type = rng.choice(["RightFoot", "LeftFoot", "Head", "OtherBodyPart"])
                    xg_total += xg

                    # Exactly `goals` of this player's shots end up as goals, so
                    # fact_shots and fact_player_events.goals agree.
                    if scored_left > 0:
                        result = "Goal"
                        scored_left -= 1
                    else:
                        # The full vocabulary Understat uses, measured against the
                        # real snapshot (trap 11). `MissedShots` really is the only
                        # plural one. `OwnGoal` is a value of `result` too, and is
                        # added as an explicit row below rather than drawn at random,
                        # because it has to stay consistent with a scoreline.
                        result = rng.choice(
                            ["SavedShot", "MissedShots", "BlockedShot", "ShotOnPost"]
                        )

                    shots.append(
                        {
                            "shot_key": shot_id,
                            "understat_shot_id": shot_id,
                            "understat_match_id": entry["understat_match_id"],
                            "match_key": entry["match_key"],
                            "player_key": player_key,
                            "team_key": team,
                            "assist_player_key": None,
                            "minute": rng.randint(1, 90),
                            "is_home": is_home,
                            "x": x,
                            "y": y,
                            "xg": xg,
                            "result": result,
                            "situation": situation,
                            "shot_type": shot_type,
                        }
                    )

                events.append(
                    {
                        "player_event_key": len(events) + 1,
                        "understat_match_id": entry["understat_match_id"],
                        "understat_player_id": us_player_id,
                        "match_key": entry["match_key"],
                        "player_key": player_key,
                        "team_key": team,
                        "match_date": entry["match_date"],
                        "position": position,
                        "minutes_played": rng.choice([90, 90, 90, 78, 64]),
                        "goals": goals,
                        "own_goals": 0,
                        "assists": rng.randint(0, 1),
                        "shots": n_shots,
                        "key_passes": rng.randint(0, 3),
                        "xg": round(xg_total, 4),
                        "xa": round(rng.uniform(0.0, 0.6), 4),
                        "xg_chain": round(xg_total + rng.uniform(0.0, 0.5), 4),
                        "xg_buildup": round(rng.uniform(0.0, 0.4), 4),
                        "yellow_cards": 1 if rng.random() < 0.12 else 0,
                        "red_cards": 0,
                    }
                )

    # --- trap 11: OwnGoal is a value of `result`, not a separate table ------
    # Measured against the real snapshot: an OwnGoal row sits on the team of the
    # player who put it in their own net, and counts as a goal for the *opponent* —
    # reconstructing each side's goals from shots comes to within 1 in 5,684 that
    # way. So `result = 'Goal'` correctly excludes own goals, but any "on target"
    # proxy built by excluding misses silently counts them. It carries no xG worth
    # the name, and the scorer's `own_goals` below is what records it.
    own_goal_entry = plan[1]
    shot_id += 1
    shots.append(
        {
            "shot_key": shot_id,
            "understat_shot_id": shot_id,
            "understat_match_id": own_goal_entry["understat_match_id"],
            "match_key": own_goal_entry["match_key"],
            "player_key": squad_for(own_goal_entry["home"], own_goal_entry["match_date"])[0][0],
            "team_key": own_goal_entry["home"],
            "assist_player_key": None,
            "minute": 71,
            "is_home": True,
            "x": 0.1200,
            "y": 0.5100,
            "xg": 0.0100,
            "result": "OwnGoal",
            "situation": "OpenPlay",
            "shot_type": "OtherBodyPart",
        }
    )
    for event in events:
        if (
            event["match_key"] == own_goal_entry["match_key"]
            and event["team_key"] == own_goal_entry["home"]
        ):
            event["own_goals"] = 1
            break

    # --- trap 14: Understat returned one match's shots twice ---------------
    # Same shot, different shot id. Anything that sums shot volume or xG without
    # deduplicating on (match, player, minute, result, x, y, xg) doubles here.
    duplicated = [s for s in shots if s["match_key"] == plan[0]["match_key"]][:2]
    for original in duplicated:
        shot_id += 1
        shots.append({**original, "shot_key": shot_id, "understat_shot_id": shot_id})

    # --- trap 4: events and shots whose match was never matched -----------
    # Understat has the rows, but the cross-source join never produced a
    # fact_matches row, so match_key is NULL. An inner join drops these silently.
    events.append(
        {
            "player_event_key": len(events) + 1,
            "understat_match_id": 999_001,
            "understat_player_id": 101,
            "match_key": None,
            "player_key": 1,
            "team_key": 1,
            "match_date": date(2026, 8, 22),
            "position": "F M S",
            "minutes_played": 90,
            "goals": 1,
            "own_goals": 0,
            "assists": 0,
            "shots": 3,
            "key_passes": 1,
            "xg": 0.4100,
            "xa": 0.0500,
            "xg_chain": 0.6200,
            "xg_buildup": 0.1100,
            "yellow_cards": 0,
            "red_cards": 0,
        }
    )
    shot_id += 1
    shots.append(
        {
            "shot_key": shot_id,
            "understat_shot_id": shot_id,
            "understat_match_id": 999_001,
            "match_key": None,
            "player_key": 1,
            "team_key": 1,
            "assist_player_key": None,
            "minute": 55,
            "is_home": True,
            "x": 0.9100,
            "y": 0.4800,
            "xg": 0.2300,
            "result": "Goal",
            "situation": "OpenPlay",
            "shot_type": "LeftFoot",
        }
    )
    return events, shots


# --- writing ---------------------------------------------------------------


def write_table(
    con: duckdb.DuckDBPyConnection,
    table: str,
    rows: list[dict[str, Any]],
    columns: list[gold.Column],
    out_dir: Path,
) -> dict[str, object]:
    """Write one table to Parquet, in the contract's column order and types.

    Rows are dicts: a column the fixture does not set becomes NULL, and a key
    the contract does not know about is an error rather than a silent drop.
    """
    names = [c.name for c in columns]
    known = set(names)
    for row in rows:
        unknown = set(row) - known
        if unknown:
            raise SystemExit(
                f"{table}: fixture sets columns that are not in the contract: "
                f"{sorted(unknown)}. Did Part 1 rename them?"
            )

    col_defs = ", ".join(f'"{c.name}" {duckdb_type(c.type)}' for c in columns)
    placeholders = ", ".join(["?"] * len(names))
    con.execute(f"CREATE OR REPLACE TABLE stage_{table} ({col_defs})")
    con.executemany(
        f"INSERT INTO stage_{table} VALUES ({placeholders})",
        [
            tuple(row.get(name, LOADED_AT if name == "loaded_at" else None) for name in names)
            for row in rows
        ],
    )

    target = out_dir / f"{table}.parquet"
    con.execute(f"COPY stage_{table} TO '{target}' (FORMAT PARQUET, COMPRESSION zstd)")
    return {"file": target.name, "rows": len(rows), "bytes": target.stat().st_size}


def main() -> int:
    rng = random.Random(SEED)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    contract = gold.load_contract()
    matches, plan = build_matches(rng)
    events, shots = build_events_and_shots(rng, plan)

    data = {
        "dim_teams": TEAMS,
        "dim_players": PLAYERS,
        "dim_referees": REFEREES,
        "dim_stadiums": STADIUMS,
        "fact_matches": matches,
        "fact_player_events": events,
        "fact_shots": shots,
    }

    missing = set(contract) - set(data)
    if missing:
        raise SystemExit(
            f"The contract has tables the fixture does not build: {sorted(missing)}. "
            "Part 1 added a Gold table; teach this generator about it."
        )

    con = duckdb.connect(database=":memory:")
    for stale in sorted([*OUT_DIR.glob("*.parquet"), *OUT_DIR.glob("manifest.json")]):
        stale.unlink()

    tables: dict[str, dict[str, object]] = {}
    for table in sorted(data):
        tables[table] = write_table(con, table, data[table], contract[table], OUT_DIR)
        print(f"  {table:<20} {tables[table]['rows']:>6,} rows")

    lo, hi = con.execute(
        "SELECT min(match_date), max(match_date) FROM stage_fact_matches"
    ).fetchone()
    manifest = {
        "exported_at": LOADED_AT,
        "source": "synthetic fixture (tests/fixtures/make_gold_fixture.py)",
        "duckdb_version": duckdb.__version__,
        "contract": "contracts/gold_columns.json",
        "match_date_range": {"min": lo.isoformat(), "max": hi.isoformat()},
        "tables": tables,
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {OUT_DIR}/manifest.json - matches {lo} to {hi}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
