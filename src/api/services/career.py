# src/api/services/career.py
#
# Each person's career record, for their profile page (/gms/{username},
# plans/gm-profile-page.md). One gm_career_seasons row per league season they
# ran a team in: the regular season W-L, a division title, and how far they
# got in the playoffs.
#
# The rows are copied out of the league rather than worked out from it when
# the page is shown, because the league doesn't keep them: someone who leaves
# hands their team to an AI GM, and the league is deleted when its last
# person leaves. So the record is kept up to date as the league runs, after
# every sim job (sim_jobs.run), and written one last time when a person
# leaves (leave_league), which is also before any league is deleted.
#
# A season's row is final once the season is over, or once the person has
# left; a final row never changes again. Tutorial leagues and backstory
# seasons don't count.

from __future__ import annotations

from src.db.repositories.career_repo import CareerRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.series_repo import SeriesRepository
from src.db.repositories.standings_repo import StandingsRepository
from src.db.repositories.team_game_repo import TeamGameRepository
from src.league import divisions

# How far a team got, from its deepest playoff series (series.name).
ROUND_OF_SERIES = {
    "1v8": "Round 1",
    "2v7": "Round 1",
    "3v6": "Round 1",
    "4v5": "Round 1",
    "[1,8]v[4,5]": "Semifinals",
    "[2,7]v[3,6]": "Semifinals",
    "Finals": "Finals",
}
ROUND_DEPTH = {"Round 1": 1, "Semifinals": 2, "Finals": 3, "Champion": 4}


def record_league(conn, league_id: str, leaving_gm_id: str | None = None) -> None:
    """Bring every person's rows in the league up to date. With
    ``leaving_gm_id``, only that GM's, and their rows are made final since
    they're leaving."""
    league = conn.execute(
        "SELECT id, name, state, is_practice FROM leagues WHERE id = %s",
        (league_id,),
    ).fetchone()
    if not league or league["is_practice"] or league["state"] == "lobby":
        return
    gms = _people(conn, league_id, leaving_gm_id)
    if not gms:
        return
    repo = CareerRepository(conn)
    repo.rename_league(league_id, league["name"])
    seasons = sorted(
        (s for s in SeasonRepository(conn).get_seasons_for_league(league_id)
         if not s["is_backstory"]),
        key=lambda s: s["year"],
    )  # fmt: skip
    done = {g["id"]: repo.final_season_ids(g["user_id"], league_id) for g in gms}
    for i, season in enumerate(seasons):
        todo = [g for g in gms if season["id"] not in done[g["id"]]]
        if not todo:
            continue
        later_season = i < len(seasons) - 1
        facts = _SeasonFacts(conn, league_id, season["id"])
        over = (
            facts.champion_id is not None
            or later_season
            or league["state"] == "complete"
        )
        for gm in todo:
            wl = TeamGameRepository(conn).get_team_wl(gm["team_id"], season["id"])
            if wl is None:
                continue  # no games yet
            repo.save(
                {
                    "user_id": gm["user_id"],
                    "league_id": league_id,
                    "season_id": season["id"],
                    "league_name": league["name"],
                    "season_year": season["year"],
                    "team_city": gm["city"],
                    "team_mascot": gm["mascot"],
                    "wins": wl["w"],
                    "losses": wl["l"],
                    "division_title": gm["team_id"] in facts.division_winners,
                    "playoff_result": facts.playoff_result(gm["team_id"]),
                    "final": over or leaving_gm_id is not None,
                }
            )


def backfill(conn) -> None:
    """Fill the records from every league that's still around."""
    rows = conn.execute(
        "SELECT id FROM leagues WHERE NOT is_practice AND state <> 'lobby'"
    ).fetchall()
    for r in rows:
        record_league(conn, r["id"])


def _people(conn, league_id: str, gm_id: str | None) -> list[dict]:
    """The league's human GMs with their teams (or just ``gm_id``)."""
    sql = """SELECT g.id, g.user_id, g.team_id, t.city, t.mascot
             FROM gms g JOIN teams t ON t.id = g.team_id
             WHERE g.league_id = %s AND g.user_id IS NOT NULL AND NOT g.is_ai"""
    params: tuple = (league_id,)
    if gm_id:
        sql += " AND g.id = %s"
        params += (gm_id,)
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


class _SeasonFacts:
    """What one season says about every team: the champion, division
    winners (once the regular season is over) and playoff series."""

    def __init__(self, conn, league_id: str, season_id: str):
        champ = SeriesRepository(conn).get_champion(season_id)
        self.champion_id = champ["team_id"] if champ else None
        self.division_winners = (
            _division_winners(conn, league_id, season_id)
            if _regular_season_over(conn, season_id)
            else set()
        )
        rows = conn.execute(
            """SELECT DISTINCT s.name, t.team_id
               FROM series s JOIN games g ON g.series_id = s.id
               CROSS JOIN LATERAL (VALUES (g.home_team_id), (g.away_team_id)) AS t(team_id)
               WHERE s.season_id = %s""",
            (season_id,),
        ).fetchall()
        self.deepest: dict[str, str] = {}
        for r in rows:
            reached = ROUND_OF_SERIES.get(r["name"])
            if not reached:
                continue
            best = self.deepest.get(r["team_id"])
            if best is None or ROUND_DEPTH[reached] > ROUND_DEPTH[best]:
                self.deepest[r["team_id"]] = reached

    def playoff_result(self, team_id: str) -> str | None:
        if team_id == self.champion_id:
            return "Champion"
        return self.deepest.get(team_id)


def _regular_season_over(conn, season_id: str) -> bool:
    row = conn.execute(
        """SELECT COUNT(*) AS games,
                  COUNT(*) FILTER (WHERE completed = 0 OR completed IS NULL) AS left_to_play
           FROM games WHERE season_id = %s AND series_id IS NULL""",
        (season_id,),
    ).fetchone()
    return row["games"] > 0 and row["left_to_play"] == 0


def _division_winners(conn, league_id: str, season_id: str) -> set[str]:
    """The best team in each division, by the standings' own order. Empty
    for a league without divisions."""
    conferences = divisions.load(conn, league_id)
    if not conferences:
        return set()
    place = {
        r["team_id"]: i
        for i, r in enumerate(StandingsRepository(conn).ranked(season_id))
    }
    winners = set()
    for conf in conferences:
        for div in conf.divisions:
            teams = [t for t in div.team_ids if t in place]
            if teams:
                winners.add(min(teams, key=place.get))
    return winners
