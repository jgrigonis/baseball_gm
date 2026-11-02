# src/league/trades/draft_picks.py
#
# Draft picks in trades (plans/trades.md, section 9). Only in leagues with
# pick_trades on (off by default, since MLB doesn't allow it).
#
# A pick is a team's pick in one round of one year's draft, and the one in
# play is always the next draft that hasn't run: during the season, the one
# after it; in the offseason, the one coming up, until it runs. Only the first
# TRADEABLE_ROUNDS rounds trade, since later picks are worth next to nothing.
# draft_pick_rights says who owns each pick; rows are written for a draft
# the first time anyone looks at its picks, and the draft (snake_draft.py)
# gives each pick to its owner.
#
# In an offer a pick travels as an id like a player's, "pick:<year>:<round>:
# <original team>", so offers, counters and the offer builder handle both
# alike.
#
# The AI values a pick as the prospect it's expected to bring: about the
# rating drafted players of that round have (ROUND_RATING), a little better
# early in the round and worse late, with the slot projected from the
# standings (worst record picks first, snake order). It counts for the
# future only, so a contender gives up little for one and a seller wants them.

from __future__ import annotations

from dataclasses import dataclass

from src.db.repositories.pick_rights_repo import PickRightsRepository
from src.db.repositories.standings_repo import StandingsRepository
from src.league.trade_deadline import trades_enabled_for
from src.league.trades.ai_evaluator import Asset

PICK_PREFIX = "pick"
TRADEABLE_ROUNDS = 5
# Rounds the draft has (src/league/offseason/snake_draft.py ROUNDS).
DRAFT_ROUNDS = 20
# The average rating of a round's draftees, from the drafts played so far.
ROUND_RATING = {1: 64, 2: 61, 3: 60, 4: 59, 5: 59}
# The round's first pick is this much better than its average, the last this
# much worse.
SLOT_SPREAD = 2.0
PICK_AGE = 21
ORDINALS = {1: "1st", 2: "2nd", 3: "3rd"}


@dataclass(frozen=True)
class Pick:
    draft_year: int
    round: int
    original_team_id: str

    @property
    def id(self) -> str:
        return f"{PICK_PREFIX}:{self.draft_year}:{self.round}:{self.original_team_id}"


def is_pick(asset_id: str) -> bool:
    return asset_id.startswith(PICK_PREFIX + ":")


def parse(asset_id: str) -> Pick | None:
    """The pick an id names, or None if it isn't a well-formed pick id."""
    parts = asset_id.split(":", 3)
    if len(parts) != 4 or parts[0] != PICK_PREFIX:
        return None
    try:
        return Pick(int(parts[1]), int(parts[2]), parts[3])
    except ValueError:
        return None


def enabled(league: dict) -> bool:
    return bool(league.get("pick_trades")) and trades_enabled_for(league)


def draft_year(conn, league: dict, season_year: int | None) -> int | None:
    """The year of the next draft that hasn't run: the one whose picks trade."""
    if season_year is None:
        return None
    if league.get("state") == "draft":
        # The league's draft is this season's, until it's done.
        draft = PickRightsRepository(conn).draft_for_year(league["id"], season_year)
        if draft and draft["state"] != "complete":
            return season_year
    return season_year + 1


def ensure_rights(conn, league_id: str, year: int, team_ids) -> None:
    PickRightsRepository(conn).ensure(league_id, year, team_ids, DRAFT_ROUNDS)


def owned(conn, league_id: str, year: int, team_id: str) -> list[Pick]:
    """A team's tradeable picks in a year's draft."""
    return [
        Pick(year, r["round"], r["original_team_id"])
        for r in PickRightsRepository(conn).owned_by(
            league_id, year, team_id, TRADEABLE_ROUNDS
        )
    ]


def owner(conn, league_id: str, pick: Pick) -> str | None:
    return PickRightsRepository(conn).owner(
        league_id, pick.draft_year, pick.round, pick.original_team_id
    )


def move(conn, league_id: str, pick: Pick, to_team_id: str) -> None:
    PickRightsRepository(conn).move(
        league_id, pick.draft_year, pick.round, pick.original_team_id, to_team_id
    )


def projected_slots(
    conn, league_id: str, season_id: str, year: int
) -> tuple[dict[str, int], int]:
    """({team_id: first-round slot}, teams): the draft's own order once it's
    set, otherwise the standings, worst record first. Before anyone has
    played, every team sits in the middle."""
    repo = PickRightsRepository(conn)
    draft = repo.draft_for_year(league_id, year)
    if draft:
        positions = repo.draft_positions(draft["id"])
        if positions:
            return positions, len(positions)
    rows = StandingsRepository(conn).get_records(league_id, season_id)

    def pct(r):
        played = r["wins"] + r["losses"]
        return r["wins"] / played if played else 0.5

    if not any(r["wins"] + r["losses"] for r in rows):
        return {r["team_id"]: (len(rows) + 1) // 2 for r in rows}, len(rows)
    ranked = sorted(rows, key=lambda r: (pct(r), r["team_id"]))
    return {r["team_id"]: i for i, r in enumerate(ranked, 1)}, len(ranked)


def slot_in_round(pick: Pick, first_round_slot: int, teams: int) -> int:
    """Snake order: even rounds run the other way."""
    if pick.round % 2 == 0:
        return teams + 1 - first_round_slot
    return first_round_slot


def expected_rating(pick: Pick, first_round_slot: int, teams: int) -> float:
    slot = slot_in_round(pick, first_round_slot, teams)
    share = (slot - 1) / (teams - 1) if teams > 1 else 0.5
    return ROUND_RATING[pick.round] + SLOT_SPREAD * (1 - 2 * share)


def label(pick: Pick, team_name: str) -> str:
    """'2026 1st round (Dubai Falcons)'."""
    nth = ORDINALS.get(pick.round, f"{pick.round}th")
    return f"{pick.draft_year} {nth} round ({team_name})"


def asset(pick: Pick, first_round_slot: int, teams: int, team_name: str) -> Asset:
    """The pick as the AI sees it: the prospect it's expected to bring."""
    rating = round(expected_rating(pick, first_round_slot, teams))
    return Asset(
        id=pick.id,
        name=label(pick, team_name),
        is_pitcher=False,
        hit=rating,
        sp=rating,
        rp=rating,
        age=PICK_AGE,
        future_only=True,
    )
