# src/api/services/badges.py
#
# Badges on a person's GM profile (plans/gm-profile-page.md, phase 2).
#
# Each badge has a rule that looks at what the person has done: their career
# rows (gm_career_seasons, which outlive their leagues) and, for draft picks,
# All-Star games and the derby, the leagues they're still in. A badge is
# stored in gm_badges the first time its rule passes and kept from then on,
# even if what earned it is later deleted with its league.
#
# Rules are checked after every sim job for the people in that league
# (sim_jobs.run), when someone leaves a league (before the team stops being
# theirs), when an email or the paid contributor flag is set, and when an
# email is verified. Verified Email and Paid Contributor are the only badges
# that can be taken back: when the email changes, or the flag is unset.
# Tutorial leagues count only toward Rookie GM, and leagues with custom
# teams (single player, league_custom_teams) toward none.

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.db.repositories.career_repo import CareerRepository
from src.db.repositories.series_repo import SeriesRepository


@dataclass(frozen=True)
class Badge:
    key: str
    icon: str
    name: str
    description: str


@dataclass
class Check:
    """What a badge's rule found: earned or not, where it was earned, and
    how close the person is to a badge with a count to reach."""

    earned: bool
    detail: str | None = None
    progress: tuple[int, int] | None = None  # (so far, needed)


class _Person:
    """What the rules look at, loaded once per person."""

    def __init__(self, conn, user_id: str):
        self.conn = conn
        self.id = user_id
        self.user = conn.execute(
            "SELECT email, is_verified, is_contributor FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()
        # Oldest first, so the first match is where a badge was first earned.
        # A league with custom teams earns no badges (league_custom_teams).
        self.seasons = sorted(
            (
                s
                for s in CareerRepository(conn).for_user(user_id)
                if not s.get("custom_teams")
            ),
            key=lambda s: (s["season_year"], s["league_name"]),
        )

    def by_league(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for s in self.seasons:
            out.setdefault(s["league_id"], []).append(s)
        return out


def _where(s: dict) -> str:
    return f"{s['league_name']} · {s['season_year']}"


def _count(n: int, needed: int, detail: str | None = None) -> Check:
    return Check(n >= needed, detail if n >= needed else None, (min(n, needed), needed))


# ── The rules ─────────────────────────────────────────────────────────────────


def _rookie_gm(p: _Person) -> Check:
    """A tutorial league season played through the Finals."""
    rows = p.conn.execute(
        """SELECT s.id FROM gms g
           JOIN leagues l ON l.id = g.league_id AND l.is_practice
           JOIN league_seasons ls ON ls.league_id = l.id
           JOIN seasons s ON s.id = ls.season_id AND NOT s.is_backstory
           WHERE g.user_id = %s""",
        (p.id,),
    ).fetchall()
    series = SeriesRepository(p.conn)
    return Check(any(series.get_champion(r["id"]) for r in rows))


def _email(p: _Person) -> Check:
    return Check(bool(p.user and p.user["email"]))


def _verified_email(p: _Person) -> Check:
    """Clicked a verify link (email_verify.py). Taken back if the email
    changes, until the new one is verified."""
    return Check(bool(p.user and p.user["email"] and p.user["is_verified"]))


def _contributor(p: _Person) -> Check:
    return Check(bool(p.user and p.user["is_contributor"]))


def _champion(p: _Person) -> Check:
    s = next((s for s in p.seasons if s["playoff_result"] == "Champion"), None)
    return Check(s is not None, _where(s) if s else None)


def _dynasty(p: _Person) -> Check:
    best, where = 0, None
    for ss in p.by_league().values():
        titles = [s for s in ss if s["playoff_result"] == "Champion"]
        if len(titles) > best:
            best = len(titles)
            where = _where(titles[2]) if len(titles) >= 3 else None
    return _count(best, 3, where)


def _back_to_back(p: _Person) -> Check:
    for ss in p.by_league().values():
        won = {s["season_year"]: s for s in ss if s["playoff_result"] == "Champion"}
        for year, s in sorted(won.items()):
            if year + 1 in won:
                return Check(True, _where(won[year + 1]))
    return Check(False)


def _hundred_wins(p: _Person) -> Check:
    s = next((s for s in p.seasons if s["wins"] >= 100), None)
    if s:
        return Check(True, f"{_where(s)} · {s['wins']}-{s['losses']}", (100, 100))
    best = max((s["wins"] for s in p.seasons), default=0)
    return Check(False, None, (best, 100))


def _worst_to_first(p: _Person) -> Check:
    """Last in the division one season, first the next."""
    for ss in p.by_league().values():
        by_year = {s["season_year"]: s for s in ss}
        for year, s in sorted(by_year.items()):
            nxt = by_year.get(year + 1)
            if (
                nxt
                and s["finish"]
                and s["finish_of"]
                and s["finish_of"] > 1
                and s["finish"] == s["finish_of"]
                and nxt["finish"] == 1
            ):
                return Check(True, _where(nxt))
    return Check(False)


def _sweep(p: _Person) -> Check:
    s = next((s for s in p.seasons if s["sweeps"]), None)
    return Check(s is not None, _where(s) if s else None)


def _full_run(p: _Person) -> Check:
    """Every season of a league, start to finish, still running the team."""
    rows = p.conn.execute(
        """SELECT l.id, l.name,
                  (SELECT COUNT(*) FROM league_seasons ls JOIN seasons s ON s.id = ls.season_id
                   WHERE ls.league_id = l.id AND NOT s.is_backstory) AS seasons
           FROM gms g JOIN leagues l ON l.id = g.league_id
           WHERE g.user_id = %s AND l.state = 'complete' AND NOT l.is_practice AND NOT l.single_player""",
        (p.id,),
    ).fetchall()
    played = {lid: len(ss) for lid, ss in p.by_league().items()}
    for r in rows:
        if r["seasons"] and played.get(r["id"], 0) >= r["seasons"]:
            return Check(True, r["name"])
    return Check(False)


def _drafted_all_stars(p: _Person, min_round: int = 1) -> list[dict]:
    rows = p.conn.execute(
        """SELECT DISTINCT ON (dp.player_id) dp.player_id, dp.round,
                  pl.first_name, pl.last_name, l.name AS league_name
           FROM draft_picks dp
           JOIN gms g ON g.id = dp.gm_id
           JOIN leagues l ON l.id = g.league_id AND NOT l.is_practice AND NOT l.single_player
           JOIN all_stars a ON a.player_id = dp.player_id
           JOIN players pl ON pl.id = dp.player_id
           WHERE g.user_id = %s AND dp.round >= %s
           ORDER BY dp.player_id""",
        (p.id, min_round),
    ).fetchall()
    return [dict(r) for r in rows]


def _scouts_eye(p: _Person) -> Check:
    return _count(len(_drafted_all_stars(p)), 3)


def _late_round_gem(p: _Person) -> Check:
    gems = _drafted_all_stars(p, min_round=6)
    if not gems:
        return Check(False)
    g = gems[0]
    return Check(True, f"{g['first_name']} {g['last_name']}, round {g['round']}")


def _wheeler_dealer(p: _Person) -> Check:
    return _count(sum(s["trades"] for s in p.seasons), 25)


def _all_star_captain(p: _Person) -> Check:
    row = p.conn.execute(
        """SELECT l.name, s.year FROM all_star_games a
           JOIN gms g ON g.team_id IN (a.captain1_team_id, a.captain2_team_id)
           JOIN leagues l ON l.id = g.league_id AND NOT l.is_practice AND NOT l.single_player
           JOIN seasons s ON s.id = a.season_id
           WHERE g.user_id = %s AND a.state = 'played'
           ORDER BY s.year LIMIT 1""",
        (p.id,),
    ).fetchone()
    return Check(row is not None, f"{row['name']} · {row['year']}" if row else None)


def _derby_boss(p: _Person) -> Check:
    """A player of theirs won the Home Run Derby (the last round's winner)."""
    row = p.conn.execute(
        """SELECT l.name, s.year, pl.first_name, pl.last_name
           FROM hr_derby_results r
           JOIN gms g ON g.team_id = r.team_id
           JOIN leagues l ON l.id = g.league_id AND NOT l.is_practice AND NOT l.single_player
           JOIN seasons s ON s.id = r.season_id
           JOIN players pl ON pl.id = r.player_id
           WHERE g.user_id = %s AND r.won
             AND r.round = (SELECT MAX(round) FROM hr_derby_results x
                            WHERE x.season_id = r.season_id)
           ORDER BY s.year LIMIT 1""",
        (p.id,),
    ).fetchone()
    if not row:
        return Check(False)
    return Check(
        True, f"{row['first_name']} {row['last_name']} · {row['name']} · {row['year']}"
    )


def _gm_of_year(p: _Person) -> Check:
    """Named GM of the Year (src/league/awards.py)."""
    row = p.conn.execute(
        """SELECT l.name, s.year FROM season_awards a
           JOIN gms g ON g.id = a.gm_id
           JOIN leagues l ON l.id = g.league_id AND NOT l.is_practice AND NOT l.single_player
           JOIN seasons s ON s.id = a.season_id
           WHERE g.user_id = %s AND a.award = 'gm_of_year'
           ORDER BY s.year LIMIT 1""",
        (p.id,),
    ).fetchone()
    return Check(row is not None, f"{row['name']} · {row['year']}" if row else None)


# In the order the profile shows them.
BADGES: list[tuple[Badge, Callable[[_Person], Check]]] = [
    (Badge("champion", "🏆", "Champion", "Won a title"), _champion),
    (Badge("dynasty", "👑", "Dynasty", "3 titles in one league"), _dynasty),
    (Badge("back_to_back", "🔁", "Back-to-Back", "Titles in back-to-back seasons"), _back_to_back),
    (Badge("gm_of_year", "💼", "GM of the Year", "Named GM of the Year in your league"), _gm_of_year),
    (Badge("hundred_wins", "💯", "100 Wins", "A 100-win season"), _hundred_wins),
    (Badge("worst_to_first", "📈", "Worst to First", "Last in the division, then first the next season"), _worst_to_first),
    (Badge("sweep", "🧹", "Sweep", "Swept a playoff series"), _sweep),
    (Badge("full_run", "🏁", "Full Run", "Ran a team for every season of a league"), _full_run),
    (Badge("scouts_eye", "🔎", "Scout's Eye", "Drafted 3 future All-Stars"), _scouts_eye),
    (Badge("late_round_gem", "💎", "Late-Round Gem", "An All-Star picked after round 5"), _late_round_gem),
    (Badge("wheeler_dealer", "🤝", "Wheeler-Dealer", "25 trades"), _wheeler_dealer),
    (Badge("all_star_captain", "⭐", "All-Star Captain", "Ran a side in the All-Star Game"), _all_star_captain),
    (Badge("derby_boss", "💥", "Derby Boss", "Your player won the Home Run Derby"), _derby_boss),
    (Badge("rookie_gm", "🎓", "Rookie GM", "Played a tutorial league season through the Finals"), _rookie_gm),
    (Badge("email", "✉️", "Email on File", "Added an email to the account"), _email),
    (Badge("verified_email", "✅", "Verified Email", "Verified the account's email"), _verified_email),
    (Badge("contributor", "❤️", "Paid Contributor", "Supports the game"), _contributor),
]  # fmt: skip
BY_KEY = {b.key: b for b, _ in BADGES}


# ── Awarding ──────────────────────────────────────────────────────────────────


def earned(conn, user_id: str) -> dict[str, dict]:
    """The person's badges: key -> {detail, earned_at}."""
    rows = conn.execute(
        "SELECT badge, detail, earned_at FROM gm_badges WHERE user_id = %s",
        (user_id,),
    ).fetchall()
    return {r["badge"]: dict(r) for r in rows}


def check_all(conn, user_id: str) -> dict[str, Check]:
    """Every badge's rule for the person, right now."""
    p = _Person(conn, user_id)
    return {badge.key: rule(p) for badge, rule in BADGES}


def award(conn, user_id: str) -> list[str]:
    """Store any badge the person has newly earned. Returns their keys."""
    have = earned(conn, user_id)
    p = _Person(conn, user_id)
    new = []
    for badge, rule in BADGES:
        if badge.key in have:
            continue
        check = rule(p)
        if check.earned:
            conn.execute(
                """INSERT INTO gm_badges (user_id, badge, detail) VALUES (%s, %s, %s)
                   ON CONFLICT DO NOTHING""",
                (user_id, badge.key, check.detail),
            )
            new.append(badge.key)
    return new


def take_back(conn, user_id: str, key: str) -> None:
    """For a badge whose reason went away: Paid Contributor unset by an
    admin, or Verified Email after the email changed."""
    conn.execute(
        "DELETE FROM gm_badges WHERE user_id = %s AND badge = %s", (user_id, key)
    )


def award_league(conn, league_id: str) -> None:
    """Award the people in a league (tutorial leagues included)."""
    rows = conn.execute(
        """SELECT DISTINCT user_id FROM gms
           WHERE league_id = %s AND user_id IS NOT NULL AND NOT is_ai""",
        (league_id,),
    ).fetchall()
    for r in rows:
        award(conn, r["user_id"])


def award_everyone(conn) -> None:
    for r in conn.execute("SELECT id FROM users").fetchall():
        award(conn, r["id"])
