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
from src.db.repositories.contract_repo import ContractRepository
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


# A player's position in a sentence: "a 28-year-old B right fielder".
POSITION_WORDS = {
    "p": "pitcher",
    "sp": "starting pitcher",
    "rp": "reliever",
    "cp": "closer",
    "c": "catcher",
    "1b": "first baseman",
    "2b": "second baseman",
    "3b": "third baseman",
    "ss": "shortstop",
    "lf": "left fielder",
    "cf": "center fielder",
    "rf": "right fielder",
    "of": "outfielder",
    "if": "infielder",
    "dh": "designated hitter",
}


def _the_team(nm: Names, team_id: str, start: bool = False) -> str:
    """ "the Seattle Rain", for a story's body."""
    return f"{'The' if start else 'the'} {nm.full_team(team_id)}"


def _who(player, grade: str) -> str:
    """ "a 28-year-old B right fielder" ("an A- ..." when it reads that way)."""
    pos = POSITION_WORDS.get((player.position or "").lower(), player.position or "")
    age = f"{player.age}-year-old"
    article = "an" if age[0] in "8" or age.startswith(("11", "18")) else "a"
    return f"{article} {age} {grade} {pos}"


def _deal_text(deal: dict | None, year: int) -> str:
    """ " making $11.1M a season through 2028", or "" with no deal left."""
    if not deal:
        return ""
    through = deal["start_year"] + deal["years"] - 1
    if through < year:
        return ""
    return f" making {ct.format_salary(deal['salary'])} a season through {through}"


def _waiver_text(clears_on: str | None) -> str:
    return (
        f"until after the games on {clears_on}"
        if clears_on
        else "until this phase ends"
    )


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
        year = ContractRepository(conn).current_year(league_id)
        deal = ContractRepository(conn).released_deal(player.id, team_id)
        nm = Names(conn, league_id)
        on = today(conn, season_id)
        human = nm.is_human(team_id)
        name = nm.player(player.id)
        if waivers:
            where = (
                f"He's on waivers {_waiver_text(clears_on)}. Any team can put in "
                "a claim, and the one with the worst record gets him and takes "
                "over his deal."
            )
        else:
            where = "He's a free agent, and any team can sign him."
        NewsRepository(conn).add(
            league_id,
            season_id,
            on,
            "free_agency",
            f"fa-release:{on}:{player.id}",
            f"{nm.team(team_id)} release {name}",
            f"{_the_team(nm, team_id, True)} let go of {name}, "
            f"{_who(player, grade)}{_deal_text(deal, year or 0)}. {where}",
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
    who = plain(_the_team(nm, team_id, True))
    name = plain(nm.player(player.id))
    pos = _who(player, grade).split(" ", 2)[2]  # "B right fielder"
    if waivers:
        what = f"He's on waivers {_waiver_text(clears_on)}. Claim him on Free Agents."
    else:
        what = "He's a free agent now. Sign him on Free Agents."
    text = f"{who} released {name}, their {pos}. {what}"
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
        name = nm.player(player.id)
        terms = _deal_text(deal, year)
        terms = (
            f" They take over his deal,{terms.replace(' making', '', 1)}."
            if terms
            else ""
        )
        others = claimants - 1
        rivals = (
            f" {others} other team{'s' if others != 1 else ''} put in a claim, "
            "and the worst record goes first."
            if others > 0
            else ""
        )
        NewsRepository(conn).add(
            league_id,
            season_id,
            when,
            "free_agency",
            f"fa-claim:{when}:{player.id}",
            f"{nm.team(to_team)} claim {name} off waivers",
            f"{_the_team(nm, to_team, True)} picked up {name}, "
            f"{_who(player, grade)} {_the_team(nm, from_team)} released."
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
        name = nm.player(player.id)
        deal = ContractRepository(conn).released_deal(player.id, from_team)
        owed = (
            f" {_the_team(nm, from_team, True)} still pay him until he signs "
            "somewhere else."
            if deal and deal.get("guaranteed")
            else ""
        )
        NewsRepository(conn).add(
            league_id,
            season_id,
            when,
            "free_agency",
            f"fa-cleared:{when}:{player.id}",
            f"{name} clears waivers",
            f"Nobody claimed {name}, {_who(player, grade)} "
            f"{_the_team(nm, from_team)} released, so he's a free agent any "
            f"team can sign.{owed}",
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
        name = nm.player(player.id)
        if released_by == team_id:
            former = " He's back with the team that released him."
        elif released_by:
            former = f" {_the_team(nm, released_by, True)} released him earlier."
        else:
            former = ""
        seasons = f"season{'s' if deal.years != 1 else ''}"
        NewsRepository(conn).add(
            league_id,
            season_id,
            on,
            "free_agency",
            f"fa-sign-now:{on}:{player.id}",
            f"{nm.team(team_id)} sign free agent {name}",
            f"{_the_team(nm, team_id, True)} signed {name}, {_who(player, grade)}, "
            f"for {ct.format_salary(deal.salary)} a season over {deal.years} "
            f"{seasons}.{former}",
            weight=_weight(grade, human),
            team_ids=[team_id]
            + ([released_by] if released_by and released_by != team_id else []),
            player_ids=[player.id],
            gm_ids=nm.gm_ids(team_id, released_by if released_by != team_id else None),
        )

    _write(league_id, conn, "signing", write)
