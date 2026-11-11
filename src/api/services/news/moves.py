# src/api/services/news/moves.py
"""
News for players changing teams outside trades and offseason bidding:
releases, waiver claims, players clearing waivers, and free agent signings
in the preseason and season (Josh, 2026-11-11: "When a high rated player
gets picked up in free agency, there should be a news blurb, especially if
it was off waivers. I released my best player as a test, and now I don't
even know who got him").

A move gets a story when the player is NOTABLE_GRADE or better (the letter
a GM sees on the Roster tab), or when a person's team let him go, so a GM
always finds out where his released players end up.

Every writer here runs in a savepoint and logs a problem instead of
raising, so a story can never undo the move itself.
"""

from __future__ import annotations

import logging
from datetime import date

from src.api.grade_curves import GRADES, overall_to_grade
from src.api.services.news.names import Names, plain
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.news_repo import NewsRepository
from src.db.repositories.notification_repo import NotificationRepository
from src.db.repositories.season_repo import SeasonRepository
from src.player import contracts as ct
from src.player.player_evaluator import PlayerEvaluator

log = logging.getLogger(__name__)

# The same bar as a free agent departure story (offseason_fa).
NOTABLE_GRADE = "B-"


def shown_grade(player) -> str:
    """The overall letter a GM sees for a signed player (as on the Roster
    tab: best of SP/RP on the pitcher curve, overall on the hitter curve)."""
    r = PlayerEvaluator.rate_player(player.skills, player.throws)
    if player.is_pitcher():
        return overall_to_grade(max(r["sp"], r["rp"]), "pitcher")
    return overall_to_grade(r["overall_player"], "hitter")


def is_notable(grade: str) -> bool:
    return GRADES.index(grade) <= GRADES.index(NOTABLE_GRADE)


def _weight(grade: str, human: bool) -> int:
    return 3 if human or grade.startswith("A") else 2


def today(conn, season_id: str | None) -> str:
    """The league's date for a move made between sim days: the last day
    played this season (playoffs too), else opening day, else today."""
    if season_id:
        row = conn.execute(
            """SELECT MAX(game_date) FILTER (WHERE completed = 1) AS last,
                      MIN(game_date) AS first
               FROM games WHERE season_id = %s""",
            (season_id,),
        ).fetchone()
        if row and (row["last"] or row["first"]):
            return row["last"] or row["first"]
    return date.today().isoformat()


def _write(league_id: str, conn, what: str, fn) -> None:
    try:
        with conn.transaction():
            fn()
    except Exception:
        log.exception("League %s: couldn't write %s news", league_id, what)


def _describe(player, grade: str) -> str:
    return f"{grade} {player.position}, age {player.age}"


def released(
    conn,
    league_id: str,
    team_id: str,
    player,
    waivers: bool,
    clears_on: str | None = None,
) -> None:
    """A team released a notable player. When a person's team did, every
    other person in the league gets a notification too, so they can put in
    a claim before he clears (Josh, 2026-11-11)."""

    def write():
        grade = shown_grade(player)
        if not is_notable(grade):
            return
        season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
        nm = Names(conn, league_id)
        on = today(conn, season_id)
        human = nm.is_human(team_id)
        where = (
            "He goes on waivers; any team can claim him and take over his deal."
            if waivers
            else "He's a free agent; any team can sign him."
        )
        NewsRepository(conn).add(
            league_id,
            season_id,
            on,
            "free_agency",
            f"fa-release:{on}:{player.id}",
            f"The {nm.gm_team(team_id)} release {nm.player(player.id)}",
            f"{_describe(player, grade)}. {where}",
            weight=_weight(grade, human),
            team_ids=[team_id],
            player_ids=[player.id],
            gm_ids=nm.gm_ids(team_id),
        )
        if human:
            _tell_people(
                conn, league_id, nm, team_id, player, grade, waivers, clears_on
            )

    _write(league_id, conn, "release", write)


def _tell_people(conn, league_id, nm, team_id, player, grade, waivers, clears_on):
    """A notification for each other person running a team in the league."""
    who = plain(nm.gm_team(team_id))
    name = plain(nm.player(player.id))
    if waivers:
        until = f"after the games on {clears_on}" if clears_on else "this phase ends"
        what = f"He's on waivers until {until}. Claim him on Free Agents."
    else:
        what = "He's a free agent now. Sign him on Free Agents."
    text = f"The {who} released {name} ({grade} {player.position}). {what}"
    notes = NotificationRepository(conn)
    for gm_id, team in GMRepository(conn).get_human_gm_teams(league_id).items():
        if team == team_id or not nm.is_human(team) or nm.gm_of(team)["id"] != gm_id:
            continue
        notes.add(gm_id, "waivers", {"text": text, "player_id": player.id})


def claimed(
    conn,
    league_id: str,
    season_id: str,
    player,
    from_team: str,
    to_team: str,
    deal: dict | None,
    claimants: int,
    year: int,
    on: str | None,
) -> None:
    """A team claimed him off waivers."""

    def write():
        nm = Names(conn, league_id)
        grade = shown_grade(player)
        human = nm.is_human(from_team) or nm.is_human(to_team)
        if not (is_notable(grade) or nm.is_human(from_team)):
            return
        when = on or today(conn, season_id)
        left = deal and deal["start_year"] + deal["years"] - year
        if deal and left and left > 0:
            terms = (
                f" They take over his deal: {ct.format_salary(deal['salary'])} a "
                f"season through {deal['start_year'] + deal['years'] - 1}."
            )
        else:
            terms = ""
        others = claimants - 1
        rivals = (
            f" {others} other team{'s' if others != 1 else ''} put in a claim; "
            "the worst record goes first."
            if others > 0
            else ""
        )
        NewsRepository(conn).add(
            league_id,
            season_id,
            when,
            "free_agency",
            f"fa-claim:{when}:{player.id}",
            f"The {nm.gm_team(to_team)} claim {nm.player(player.id)} off waivers",
            f"{_describe(player, grade)}, released by the {nm.gm_team(from_team)}."
            f"{terms}{rivals}",
            weight=_weight(grade, human),
            team_ids=[to_team, from_team],
            player_ids=[player.id],
            gm_ids=nm.gm_ids(to_team, from_team),
        )

    _write(league_id, conn, "waiver claim", write)


def cleared(
    conn,
    league_id: str,
    season_id: str,
    player,
    from_team: str,
    on: str | None,
) -> None:
    """Nobody claimed him: he's a free agent."""

    def write():
        nm = Names(conn, league_id)
        grade = shown_grade(player)
        human = nm.is_human(from_team)
        if not (is_notable(grade) or human):
            return
        when = on or today(conn, season_id)
        NewsRepository(conn).add(
            league_id,
            season_id,
            when,
            "free_agency",
            f"fa-cleared:{when}:{player.id}",
            f"{nm.player(player.id)} clears waivers",
            f"{_describe(player, grade)}, released by the {nm.gm_team(from_team)}. "
            "Nobody claimed him, so he's a free agent any team can sign. "
            f"The {nm.team(from_team)} keep paying what they owe him until he does.",
            weight=_weight(grade, human),
            team_ids=[from_team],
            player_ids=[player.id],
            gm_ids=nm.gm_ids(from_team),
        )

    _write(league_id, conn, "waivers cleared", write)


def last_released_by(conn, league_id: str, player_id: str) -> str | None:
    """The team that released him from his newest deal, if it was released."""
    row = conn.execute(
        """SELECT released_team_id FROM player_contracts
           WHERE player_id = %s AND league_id = %s
           ORDER BY start_year DESC, id DESC LIMIT 1""",
        (player_id, league_id),
    ).fetchone()
    return row["released_team_id"] if row else None


def signed(
    conn,
    league_id: str,
    season_id: str,
    player,
    team_id: str,
    deal: ct.Deal,
    released_by: str | None,
) -> None:
    """A team signed a free agent at his asking price."""

    def write():
        nm = Names(conn, league_id)
        grade = shown_grade(player)
        human = nm.is_human(team_id) or nm.is_human(released_by)
        if not (is_notable(grade) or nm.is_human(released_by)):
            return
        on = today(conn, season_id)
        if released_by == team_id:
            former = f" He's back with the {nm.team(team_id)}, who released him."
        elif released_by:
            former = f" The {nm.gm_team(released_by)} released him."
        else:
            former = ""
        seasons = f"season{'s' if deal.years != 1 else ''}"
        NewsRepository(conn).add(
            league_id,
            season_id,
            on,
            "free_agency",
            f"fa-sign-now:{on}:{player.id}",
            f"The {nm.gm_team(team_id)} sign free agent {nm.player(player.id)}",
            f"{_describe(player, grade)}, for {ct.format_salary(deal.salary)} a "
            f"season over {deal.years} {seasons}.{former}",
            weight=_weight(grade, human),
            team_ids=[team_id] + ([released_by] if released_by else []),
            player_ids=[player.id],
            gm_ids=nm.gm_ids(team_id, released_by),
        )

    _write(league_id, conn, "signing", write)
