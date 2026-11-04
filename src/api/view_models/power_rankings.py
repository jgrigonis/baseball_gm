# src/api/view_models/power_rankings.py
#
# The Power Rankings page: every team ranked by strength, roster ratings
# early in the season and more and more by run differential as games are
# played (src/league/power_rankings.py), with hitting, pitching and defense
# ranks, a trend arrow against a week ago, recent form and luck.

from __future__ import annotations

from datetime import date, timedelta

from src.api.view_models.standings import calc_streak, team_gms
from src.api.view_models.welcome import MAJORS, ordinal
from src.db.repositories.draft_repo import DraftRepository
from src.db.repositories.gm_repo import GMRepository
from src.league.offseason.draft_strategy import ratings, staff_groups
from src.league.power_rankings import (
    AREAS,
    power_scores,
    results_weight,
    team_strength,
)

TREND_DAYS = 7
LUCK_MIN_GAMES = 20  # luck is noise before this
PYTHAG_EXP = 1.83

AREA_LABELS = {"hitting": "Hitting", "pitching": "Pitching", "defense": "Defense"}
AREA_TIPS = {
    "hitting": "Starting lineup's contact, power and eye, plus runs scored",
    "pitching": "Rotation and bullpen control and stuff, plus runs allowed",
    "defense": "Gloves at the positions played and the fielders' arms",
}


def _teams(db, league_id: str, season_id: str) -> list[dict]:
    return db.execute(
        """SELECT t.id AS team_id, t.city, t.mascot
           FROM league_season_teams lst JOIN teams t ON t.id = lst.team_id
           WHERE lst.league_id = %s AND lst.season_id = %s""",
        (league_id, season_id),
    ).fetchall()


def _games(db, season_id: str) -> list[dict]:
    """The season's played regular-season games, oldest first."""
    return db.execute(
        """SELECT game_date, home_team_id, away_team_id, home_score, away_score
           FROM games
           WHERE season_id = %s AND series_id IS NULL AND completed = 1
           ORDER BY game_date, id""",
        (season_id,),
    ).fetchall()


def records(games: list[dict], before: str | None = None) -> dict[str, dict]:
    """{team_id: {g, w, l, rs, ra, results}} from games (dated before
    `before` when given). results is win/loss, most recent first."""
    out: dict[str, dict] = {}
    for g in games:
        if before and g["game_date"] >= before:
            continue
        sides = (
            (g["home_team_id"], g["home_score"], g["away_score"]),
            (g["away_team_id"], g["away_score"], g["home_score"]),
        )
        for team, scored, allowed in sides:
            r = out.setdefault(
                team, {"g": 0, "w": 0, "l": 0, "rs": 0, "ra": 0, "results": []}
            )
            won = scored > allowed
            r["g"] += 1
            r["w" if won else "l"] += 1
            r["rs"] += scored or 0
            r["ra"] += allowed or 0
            r["results"].insert(0, won)
    return out


def ranks(values: dict[str, float]) -> dict[str, int]:
    """1 = highest value."""
    order = sorted(values, key=values.get, reverse=True)
    return {t: i for i, t in enumerate(order, 1)}


def rank_grade(rank: int, n: int) -> str:
    """A letter for the grade colors, by where a rank falls in the league."""
    if n <= 1:
        return "B"
    share = (rank - 1) / (n - 1)
    for cut, letter in (
        (0.1, "A"),
        (0.25, "A-"),
        (0.4, "B"),
        (0.6, "C+"),
        (0.75, "C"),
        (0.9, "D"),
    ):
        if share <= cut:
            return letter
    return "F"


def expected_wins(r: dict) -> float:
    """Wins the team's runs scored and allowed are worth (Pythagorean)."""
    rs, ra = r["rs"] ** PYTHAG_EXP, r["ra"] ** PYTHAG_EXP
    return r["g"] * rs / (rs + ra) if rs + ra else r["g"] / 2


def strengths(db, team_ids: list[str]) -> dict[str, dict[str, float]]:
    draft_repo = DraftRepository(db)
    rosters = draft_repo.get_roster_records(team_ids)
    staff = draft_repo.get_staff_groups(team_ids)
    out = {}
    for tid in team_ids:
        rated = [
            (p, ratings(p)) for p, status in rosters.get(tid, []) if status in MAJORS
        ]
        groups = staff_groups([x for x in rated if x[0].is_pitcher()], staff)
        out[tid] = team_strength(rated, groups)
    return out


def power_rankings(
    db, league_id: str, season_id: str | None, my_team_id: str | None
) -> dict:
    """Everything the page shows."""
    if not season_id:
        return {"rows": [], "games": 0}
    teams = _teams(db, league_id, season_id)
    if not teams:
        return {"rows": [], "games": 0}
    team_ids = [t["team_id"] for t in teams]
    strength = strengths(db, team_ids)
    games = _games(db, season_id)
    now = records(games)
    scores = power_scores(strength, now)
    power_rank = ranks({t: s["power"] for t, s in scores.items()})
    area_rank = {a: ranks({t: s[a] for t, s in scores.items()}) for a in AREAS}

    # A week ago: the same rosters, the results up to then.
    trend = {}
    if games:
        last = date.fromisoformat(games[-1]["game_date"][:10])
        cutoff = (last - timedelta(days=TREND_DAYS - 1)).isoformat()
        then = records(games, before=cutoff)
        if then:
            before = power_scores(strength, then)
            before_rank = ranks({t: s["power"] for t, s in before.items()})
            trend = {t: before_rank[t] - power_rank[t] for t in team_ids}

    gms = team_gms(db, league_id)
    humans = GMRepository(db).get_human_team_ids(league_id)
    n = len(team_ids)
    rows = []
    for t in teams:
        tid = t["team_id"]
        r = now.get(tid, {"g": 0, "w": 0, "l": 0, "rs": 0, "ra": 0, "results": []})
        recent = r["results"][:10]
        luck = None
        if r["g"] >= LUCK_MIN_GAMES:
            luck = round(r["w"] - expected_wins(r))
        rows.append(
            {
                "team_id": tid,
                "city": t["city"],
                "mascot": t["mascot"],
                "rank": power_rank[tid],
                "move": trend.get(tid),
                "wins": r["w"],
                "losses": r["l"],
                "run_diff": r["rs"] - r["ra"],
                "played": r["g"],
                "l10": f"{sum(recent)}-{len(recent) - sum(recent)}" if recent else None,
                "l10_wins": sum(recent),
                "l10_losses": len(recent) - sum(recent),
                "streak": calc_streak(r["results"]) if recent else None,
                "luck": luck,
                "areas": [
                    {
                        "key": a,
                        "label": AREA_LABELS[a],
                        "rank": area_rank[a][tid],
                        "rank_text": ordinal(area_rank[a][tid]),
                        "grade": rank_grade(area_rank[a][tid], n),
                    }
                    for a in AREAS
                ],
                "is_mine": tid == my_team_id,
                "is_human": tid in humans,
                "gm": gms.get(tid),
            }
        )
    rows.sort(key=lambda row: row["rank"])
    played = max((r["played"] for r in rows), default=0)
    return {
        "rows": rows,
        "games": played,
        "results_share": round(100 * results_weight(played)),
        "area_labels": [(a, AREA_LABELS[a], AREA_TIPS[a]) for a in AREAS],
        "has_trend": bool(trend),
        "show_luck": played >= LUCK_MIN_GAMES,
    }
