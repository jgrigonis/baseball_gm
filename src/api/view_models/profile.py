# src/api/view_models/profile.py
#
# A person's GM profile (/gms/{username}, plans/gm-profile-page.md): their
# career across every league, from gm_career_seasons
# (src/api/services/career.py).

from __future__ import annotations

from datetime import date

from src.api.services import badges
from src.api.services.career import ROUND_DEPTH
from src.api.view_models.profile_sections import sections
from src.api.view_models.welcome import uniforms
from src.db.repositories.career_repo import CareerRepository
from src.team.colors import TEAM_COLORS

BIO_MAX = 160

# The trophy case, best first: (what, from a season row).
TROPHIES = (
    ("Champions", lambda r: r["playoff_result"] == "Champion"),
    ("Finals", lambda r: r["playoff_result"] == "Finals"),
    ("Division", lambda r: r["division_title"]),
)

FINISH_LABEL = {
    "Champion": "Champions",
    "Finals": "Lost Finals",
    "Semifinals": "Lost Semifinals",
    "Round 1": "Lost Round 1",
}


def find_user(db, username: str) -> dict | None:
    row = db.execute(
        """SELECT id, username, display_name, created_at, bio, favorite_team
           FROM users
           WHERE lower(username) = lower(%s)""",
        (username,),
    ).fetchone()
    return dict(row) if row else None


def team_choices() -> list[tuple[str, str]]:
    """The teams someone can pick as their favorite: (city, mascot), by city."""
    return sorted(TEAM_COLORS)


def favorite_team(city: str | None) -> tuple[str, str] | None:
    """(city, mascot) for a favorite team, or None if unset or unknown."""
    return next(((c, m) for c, m in TEAM_COLORS if c == city), None) if city else None


def pct(wins: int, losses: int) -> str:
    """A win percentage the baseball way: .548, or 1.000."""
    games = wins + losses
    if not games:
        return ".000"
    p = wins / games
    return "1.000" if p >= 1 else f"{p:.3f}"[1:]


def profile_context(db, person: dict, viewer: dict) -> dict:
    seasons = CareerRepository(db).for_user(person["id"])
    wins = sum(s["wins"] for s in seasons)
    losses = sum(s["losses"] for s in seasons)
    results = [s["playoff_result"] for s in seasons]
    titles = results.count("Champion")
    career = {
        "seasons": len(seasons),
        "wins": wins,
        "losses": losses,
        "pct": pct(wins, losses),
        "playoffs": sum(1 for r in results if r),
        "finals": sum(1 for r in results if r in ("Finals", "Champion")),
        "titles": titles,
        "leagues": len({s["league_id"] for s in seasons}),
    }
    latest = seasons[0] if seasons else None
    leagues = _leagues(db, seasons, viewer)
    team = None
    if latest:
        team = _team(latest["team_city"], latest["team_mascot"])
        team["active"] = any(
            lg["league_id"] == latest["league_id"] and lg["status"] == "Active"
            for lg in leagues
        )
    favorite = favorite_team(person.get("favorite_team"))
    return {
        "person": person,
        "favorite": _team(*favorite) if favorite else None,
        "is_me": person["id"] == viewer.get("id"),
        "since": _month_year(person["created_at"]),
        "career": career,
        "team": team,
        "trophies": _trophies(seasons),
        "leagues": leagues,
        "badges": _badges(db, person["id"]),
        **sections(db, person["id"], seasons),
    }


def _badges(db, user_id: str) -> dict:
    """Every badge, earned ones first: lit with where it was earned, the
    rest dimmed, with progress for a badge that has a count to reach."""
    have = badges.earned(db, user_id)
    checks = badges.check_all(db, user_id)
    rows = []
    for badge, _ in badges.BADGES:
        got = have.get(badge.key)
        check = checks[badge.key]
        rows.append(
            {
                "icon": badge.icon,
                "name": badge.name,
                "description": badge.description,
                "earned": got is not None,
                "detail": got["detail"] if got else None,
                "progress": None if got else check.progress,
            }
        )
    rows.sort(key=lambda b: not b["earned"])  # stable: keeps the list order
    return {"all": rows, "earned": len(have), "total": len(rows)}


def _team(city: str, mascot: str) -> dict:
    u = uniforms(city)
    return {"city": city, "mascot": mascot, "patch": u["patch"] if u else None}


def _trophies(seasons: list[dict]) -> list[dict]:
    """One per title, Finals trip and division title, best first, then
    newest first. A season with a title and a division title shows both."""
    out = []
    for what, earned in TROPHIES:
        for s in seasons:
            if earned(s):
                out.append(
                    {
                        "what": what,
                        "year": s["season_year"],
                        "league_name": s["league_name"],
                        **_team(s["team_city"], s["team_mascot"]),
                    }
                )
    return out


def _leagues(db, seasons: list[dict], viewer: dict) -> list[dict]:
    """One row per league, the one played most recently first, with how it
    stands now: Active, Complete or Left (which covers a deleted league)."""
    by_league: dict[str, list[dict]] = {}
    for s in seasons:  # newest first, so each league's first row is its latest
        by_league.setdefault(s["league_id"], []).append(s)
    if not by_league:
        return []
    ids = list(by_league)
    live = {
        r["id"]: dict(r)
        for r in db.execute(
            "SELECT id, state, is_public, num_seasons FROM leagues WHERE id = ANY(%s)",
            (ids,),
        ).fetchall()
    }
    person_id = seasons[0]["user_id"]
    member_of = _leagues_with(db, person_id, ids)
    viewer_in = _leagues_with(db, viewer.get("id"), ids) if viewer.get("id") else set()

    rows = []
    for league_id, ss in by_league.items():
        latest = ss[0]
        league = live.get(league_id)
        if league and league_id in member_of:
            status = "Complete" if league["state"] == "complete" else "Active"
        else:
            status = "Left"
        best = max(
            (s["playoff_result"] for s in ss if s["playoff_result"]),
            key=ROUND_DEPTH.get,
            default=None,
        )
        best_year = (
            min(s["season_year"] for s in ss if s["playoff_result"] == best)
            if best
            else None
        )
        w = sum(s["wins"] for s in ss)
        l = sum(s["losses"] for s in ss)  # noqa: E741
        rows.append(
            {
                "league_id": league_id,
                "name": latest["league_name"],
                "city": latest["team_city"],
                "mascot": latest["team_mascot"],
                "seasons": len(ss),
                "num_seasons": league["num_seasons"]
                if league and status == "Active"
                else None,
                "wins": w,
                "losses": l,
                "pct": pct(w, l),
                "titles": sum(1 for s in ss if s["playoff_result"] == "Champion"),
                "best": f"{FINISH_LABEL[best]} {best_year}" if best else "No playoffs",
                "status": status,
                "link": bool(
                    league and (league["is_public"] or league_id in viewer_in)
                ),
            }
        )
    return rows


def _leagues_with(db, user_id: str, league_ids: list[str]) -> set[str]:
    rows = db.execute(
        "SELECT league_id FROM gms WHERE user_id = %s AND league_id = ANY(%s)",
        (user_id, league_ids),
    ).fetchall()
    return {r["league_id"] for r in rows}


def _month_year(created_at) -> str | None:
    try:
        d = date.fromisoformat(str(created_at)[:10])
    except ValueError:
        return None
    return d.strftime("%B %Y")
