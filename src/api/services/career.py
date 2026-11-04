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
#
# Head-to-head records against the other people in the league (the profile's
# Rivals section) are kept the same way, in gm_head_to_head: one row per
# person, opponent and season, written from both sides, and final once the
# season is over or either of them leaves.
#
# A person who takes over an AI GM's team in a running league (takeover.py)
# starts their record with the first season they run it, gms.joined_year.

from __future__ import annotations

from src.db.repositories.career_repo import CareerRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.series_repo import SeriesRepository
from src.db.repositories.standings_repo import StandingsRepository
from src.db.repositories.team_game_repo import TeamGameRepository
from src.db.repositories.team_state_repo import TeamStateRepository
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
    everyone = gms if leaving_gm_id is None else _people(conn, league_id, None)
    for i, season in enumerate(seasons):
        # Someone who took over a team in a running league starts with the
        # first season they ran it (gms.joined_year).
        todo = [
            g
            for g in gms
            if season["id"] not in done[g["id"]] and _was_there(g, season)
        ]
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
                    "finish": facts.finish.get(gm["team_id"], (None, None))[0],
                    "finish_of": facts.finish.get(gm["team_id"], (None, None))[1],
                    "playoff_result": facts.playoff_result(gm["team_id"]),
                    "sweeps": facts.sweeps.get(gm["team_id"], 0),
                    "trades": _trades(conn, season["id"], gm["team_id"]),
                    "front_office": facts.front_office.get(gm["team_id"]),
                    "final": over or leaving_gm_id is not None,
                }
            )
        _record_head_to_head(
            conn,
            league,
            season,
            todo,
            [g for g in everyone if _was_there(g, season)],
            over or leaving_gm_id is not None,
        )


def _was_there(gm: dict, season: dict) -> bool:
    """Whether the GM ran their team in the season."""
    return gm.get("joined_year") is None or season["year"] >= gm["joined_year"]


def backfill(conn) -> None:
    """Fill the records from every league that's still around."""
    rows = conn.execute(
        "SELECT id FROM leagues WHERE NOT is_practice AND state <> 'lobby'"
    ).fetchall()
    for r in rows:
        record_league(conn, r["id"])


def _record_head_to_head(conn, league, season, gms, everyone, final) -> None:
    """Each of ``gms`` against every other person in the league, written
    from both sides so that someone leaving closes their opponents' rows too."""
    if len(everyone) < 2:
        return
    team_of = {g["team_id"]: g for g in everyone}
    games = head_to_head(conn, season["id"], list(team_of))
    repo = CareerRepository(conn)
    pairs = {
        (g["team_id"], o["team_id"])
        for g in gms
        for o in everyone
        if o["team_id"] != g["team_id"]
    }
    pairs |= {(b, a) for a, b in pairs}
    for a, b in pairs:
        rec = games.get((a, b))
        if not rec:
            continue
        me, them = team_of[a], team_of[b]
        repo.save_head_to_head(
            {
                "user_id": me["user_id"],
                "opponent_id": them["user_id"],
                "league_id": league["id"],
                "season_id": season["id"],
                "league_name": league["name"],
                "season_year": season["year"],
                "team_city": me["city"],
                "team_mascot": me["mascot"],
                "opponent_city": them["city"],
                "opponent_mascot": them["mascot"],
                "final": final,
                **rec,
            }
        )


def head_to_head(conn, season_id: str, team_ids: list[str]) -> dict:
    """Games between the given teams in a season, as
    {(team, opponent): {wins, losses, series_round, series_won}}, where
    series_round is the playoff round they met in (decided series only)."""
    rows = conn.execute(
        """SELECT g.home_team_id, g.away_team_id, g.winner_id, g.series_id, s.name
           FROM games g LEFT JOIN series s ON s.id = g.series_id
           WHERE g.season_id = %s AND g.completed = 1 AND g.winner_id IS NOT NULL
             AND g.home_team_id = ANY(%s) AND g.away_team_id = ANY(%s)""",
        (season_id, team_ids, team_ids),
    ).fetchall()
    out: dict[tuple[str, str], dict] = {}
    series: dict[str, dict] = {}
    for r in rows:
        winner = r["winner_id"]
        loser = r["away_team_id"] if winner == r["home_team_id"] else r["home_team_id"]
        for a, b, won in ((winner, loser, True), (loser, winner, False)):
            rec = out.setdefault(
                (a, b),
                {"wins": 0, "losses": 0, "series_round": None, "series_won": None},
            )
            rec["wins" if won else "losses"] += 1
        if r["series_id"] and r["name"] in ROUND_OF_SERIES:
            sr = series.setdefault(r["series_id"], {"name": r["name"], "wins": {}})
            sr["wins"][winner] = sr["wins"].get(winner, 0) + 1
            sr["wins"].setdefault(loser, 0)
    for sr in series.values():
        round_ = ROUND_OF_SERIES[sr["name"]]
        needed = 3 if round_ == "Round 1" else 4
        (a, wa), (b, wb) = sorted(sr["wins"].items(), key=lambda kv: -kv[1])
        if wa < needed:
            continue  # not decided yet
        out[(a, b)].update(series_round=round_, series_won=True)
        out[(b, a)].update(series_round=round_, series_won=False)
    return out


def _people(conn, league_id: str, gm_id: str | None) -> list[dict]:
    """The league's human GMs with their teams (or just ``gm_id``)."""
    sql = """SELECT g.id, g.user_id, g.team_id, g.joined_year, t.city, t.mascot
             FROM gms g JOIN teams t ON t.id = g.team_id
             WHERE g.league_id = %s AND g.user_id IS NOT NULL AND NOT g.is_ai"""
    params: tuple = (league_id,)
    if gm_id:
        sql += " AND g.id = %s"
        params += (gm_id,)
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


class _SeasonFacts:
    """What one season says about every team: the champion, where each team
    finished in its division (once the regular season is over) and its
    playoff series."""

    def __init__(self, conn, league_id: str, season_id: str):
        champ = SeriesRepository(conn).get_champion(season_id)
        self.champion_id = champ["team_id"] if champ else None
        # team_id -> (place, teams), in its division, or the whole league
        # when it has no divisions.
        self.finish: dict[str, tuple[int, int]] = (
            _finishes(conn, league_id, season_id)
            if _regular_season_over(conn, season_id)
            else {}
        )
        has_divisions = bool(divisions.load(conn, league_id))
        self.division_winners = {
            t for t, (place, _) in self.finish.items() if place == 1 and has_divisions
        }
        self.sweeps = _sweeps(conn, season_id)
        # Where each front office saw its team, as of the season's last
        # checkpoint (src/league/team_state.py).
        self.front_office = {
            t: r["state"]
            for t, r in TeamStateRepository(conn).latest(league_id, season_id).items()
        }
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


def _finishes(conn, league_id: str, season_id: str) -> dict[str, tuple[int, int]]:
    """Each team's place in its division, by the standings' own order, and
    how many teams the division has. The whole league counts as one
    division in a league without divisions."""
    ranked = [r["team_id"] for r in StandingsRepository(conn).ranked(season_id)]
    place = {t: i for i, t in enumerate(ranked)}
    groups = [
        [t for t in div.team_ids if t in place]
        for conf in divisions.load(conn, league_id)
        for div in conf.divisions
    ] or [ranked]
    out = {}
    for teams in groups:
        teams.sort(key=place.get)
        for i, t in enumerate(teams, 1):
            out[t] = (i, len(teams))
    return out


def _sweeps(conn, season_id: str) -> dict[str, int]:
    """Playoff series each team won without losing a game."""
    rows = conn.execute(
        """SELECT s.id, s.name, g.winner_id, COUNT(*) AS wins
           FROM series s JOIN games g ON g.series_id = s.id AND g.completed = 1
           WHERE s.season_id = %s AND g.winner_id IS NOT NULL
           GROUP BY s.id, s.name, g.winner_id""",
        (season_id,),
    ).fetchall()
    by_series: dict[str, list[dict]] = {}
    for r in rows:
        by_series.setdefault(r["id"], []).append(r)
    out: dict[str, int] = {}
    for winners in by_series.values():
        name = winners[0]["name"]
        needed = 3 if ROUND_OF_SERIES.get(name) == "Round 1" else 4
        if len(winners) == 1 and winners[0]["wins"] >= needed:
            t = winners[0]["winner_id"]
            out[t] = out.get(t, 0) + 1
    return out


def _trades(conn, season_id: str, team_id: str) -> int:
    """Trades the team made in the season."""
    return conn.execute(
        """SELECT COUNT(*) AS n FROM trade_offers
           WHERE season_id = %s AND status = 'accepted'
             AND (from_team_id = %s OR to_team_id = %s)""",
        (season_id, team_id, team_id),
    ).fetchone()["n"]
