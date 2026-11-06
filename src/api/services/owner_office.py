# src/api/services/owner_office.py
#
# The owner's office: what each owner says to their GM, and how they feel
# (src/league/owner_messages.py). Messages are stored once, under a key, so
# writing them is safe to repeat:
#
#   pre:<season>            the preseason memo: what they want, and the budget
#   check:<season>:<n>      check-ins through the season, more if chatty
#   trade:<offer>           a reaction to a trade, if it touches what they care about
#   over:<season>           payroll went over budget
#   review:<season>         the end-of-season review and how safe the job is
#
# catch_up() writes whatever is due; the sim calls it every day it plays and
# the Owner tab when it opens. review() runs when the playoffs end, after the
# season review (owner_review.py). Mood is updated weekly in season, from the
# same scoring the review uses, on the season so far.

from __future__ import annotations

import random
from dataclasses import replace
from datetime import date

from src.api.services import owner_review
from src.api.services import owners as owner_service
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.contract_repo import ContractRepository
from src.league import budget as bg
from src.league import owner_messages as om
from src.league import owner_scoring as sc
from src.league import owners
from src.league.league_modes import get_mode
from src.player.contracts import format_salary

MOOD_DAYS = 7
# Before this many games, the record says little; mood reads it at a
# discount until then.
MOOD_FULL_GAMES = 40


def _league(conn, league_id: str) -> dict | None:
    row = conn.execute(
        "SELECT id, mode, state FROM leagues WHERE id = %s", (league_id,)
    ).fetchone()
    return dict(row) if row else None


def _season(conn, league_id: str) -> dict | None:
    row = conn.execute(
        """SELECT s.id, s.year FROM seasons s
           JOIN league_seasons ls ON ls.season_id = s.id
           WHERE ls.league_id = %s AND NOT s.is_backstory
           ORDER BY s.year DESC LIMIT 1""",
        (league_id,),
    ).fetchone()
    return dict(row) if row else None


def _gms(conn, league_id: str) -> dict[str, dict]:
    """Each team's GM now, by team id: a person's row before an AI's."""
    out: dict[str, dict] = {}
    for r in conn.execute(
        """SELECT id, team_id, display_name, is_ai FROM gms
           WHERE league_id = %s AND team_id IS NOT NULL AND fired_at IS NULL
           ORDER BY is_ai""",
        (league_id,),
    ).fetchall():
        out.setdefault(r["team_id"], dict(r))
    return out


def _team_names(conn, team_ids) -> dict[str, str]:
    rows = conn.execute(
        "SELECT id, city, mascot FROM teams WHERE id = ANY(%s)", (list(team_ids),)
    ).fetchall()
    return {r["id"]: f"{r['city']} {r['mascot']}" for r in rows}


def _rng(*parts) -> random.Random:
    return random.Random(":".join(str(p) for p in parts))


def _write(
    conn,
    league_id: str,
    team_id: str,
    gm_id: str,
    season_id: str,
    key: str,
    kind: str,
    body: str,
    on: str | None,
    mood: str | None,
) -> bool:
    row = conn.execute(
        """INSERT INTO owner_messages
               (league_id, team_id, gm_id, season_id, key, kind, body, created_on, mood)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (league_id, team_id, key) DO NOTHING
           RETURNING id""",
        (league_id, team_id, gm_id, season_id, key, kind, body, on, mood),
    ).fetchone()
    return row is not None


def _has(conn, league_id: str, team_id: str, key: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM owner_messages WHERE league_id = %s AND team_id = %s AND key = %s",
            (league_id, team_id, key),
        ).fetchone()
    )


def _recent(conn, league_id: str, team_id: str, n: int = 4) -> list[str]:
    """The team's owner's last few messages, newest first."""
    rows = conn.execute(
        """SELECT body FROM owner_messages
           WHERE league_id = %s AND team_id = %s
           ORDER BY id DESC LIMIT %s""",
        (league_id, team_id, n),
    ).fetchall()
    return [r["body"] for r in rows]


def moods(conn, league_id: str, season_id: str) -> dict[str, dict]:
    rows = conn.execute(
        """SELECT team_id, mood, as_of FROM owner_moods
           WHERE league_id = %s AND season_id = %s""",
        (league_id, season_id),
    ).fetchall()
    return {r["team_id"]: dict(r) for r in rows}


def _set_mood(conn, league_id: str, team_id: str, season_id: str, mood: float, on):
    conn.execute(
        """INSERT INTO owner_moods (league_id, team_id, season_id, mood, as_of)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (league_id, team_id, season_id)
           DO UPDATE SET mood = EXCLUDED.mood, as_of = EXCLUDED.as_of""",
        (league_id, team_id, season_id, round(mood, 4), on),
    )


def _payroll_budgets(conn, league_id: str, year: int) -> dict[str, int]:
    """Each owner's budget less what the team's front office and minor
    leagues cost: the money they're giving the GM for payroll
    (src/league/budget.py)."""
    repo = BudgetRepository(conn)
    budgets = repo.for_league(league_id, year)
    if not budgets:
        return {}
    cap = repo.cap(league_id, year)
    levels = repo.league_levels(league_id, year)
    farms = repo.league_minor_leagues(league_id, year)
    return {
        t: b - bg.front_office_cost(cap, levels.get(t, {})) - farms.get(t, 0)
        for t, b in budgets.items()
    }


def _fields(owner: dict, gm: dict, names: dict, budget: int | None) -> dict:
    rival = owner.get("rival_team_id")
    return {
        "gm": gm["display_name"] or "GM",
        "team": names.get(gm["team_id"], ""),
        "rival": names.get(rival) if rival else None,
        "budget": format_salary(budget) if budget else None,
    }


def weekly(conn, league_id: str, today: str) -> int:
    """From the sim, after a day's games: catch up once a week (the first
    day of the season, then every MOOD_DAYS)."""
    season = _season(conn, league_id)
    if not season:
        return 0
    row = conn.execute(
        """SELECT MIN(as_of) AS as_of FROM owner_moods
           WHERE league_id = %s AND season_id = %s""",
        (league_id, season["id"]),
    ).fetchone()
    if row and row["as_of"] and _days(row["as_of"], today) < MOOD_DAYS:
        return 0
    judging = conn.execute(
        "SELECT 1 FROM team_owners WHERE league_id = %s AND since_year <= %s LIMIT 1",
        (league_id, season["year"]),
    ).fetchone()
    if not judging:  # owners who arrived mid-season wait for next season
        return 0
    return catch_up(conn, league_id, today)


def catch_up(conn, league_id: str, today: str | None = None) -> int:
    """Write every message that's due, and update moods weekly in season.
    Returns how many messages were written."""
    league = _league(conn, league_id)
    season = _season(conn, league_id)
    if not league or not season or league["state"] in ("lobby", "complete"):
        return 0
    money = get_mode(league["mode"]).budgets
    by_team = owner_service.ensure(conn, league_id)
    gms = _gms(conn, league_id)
    names = _team_names(conn, by_team)
    year = season["year"]
    budgets = _payroll_budgets(conn, league_id, year) if money else {}
    written = 0
    in_season = league["state"] in ("season", "playoffs")
    played = _played(conn, season["id"]) if in_season else {}
    facts = (
        owner_review.gather(conn, league_id, season["id"], year, by_team)
        if in_season
        else {}
    )
    current = moods(conn, league_id, season["id"])
    contracts = ContractRepository(conn)
    for team_id, owner in by_team.items():
        gm = gms.get(team_id)
        if not gm or year < owner["since_year"]:
            continue
        fields = _fields(owner, gm, names, budgets.get(team_id))
        sid = season["id"]
        # The preseason memo, before or early in the season.
        if not _has(conn, league_id, team_id, f"pre:{sid}"):
            body = om.preseason(
                owner["weights"], fields, _rng(sid, team_id, "pre"), money
            )
            written += _write(
                conn, league_id, team_id, gm["id"], sid, f"pre:{sid}", "preseason",
                body, today, None,
            )  # fmt: skip
        if not in_season:
            continue
        games = played.get(team_id, 0)
        traits = owners.clean_traits(owner["traits"])
        # Mood, weekly.
        m = current.get(team_id)
        # Mid-season, money is judged on payroll against budget so far.
        so_far = replace(facts[team_id], payroll=contracts.payroll(team_id, year))
        if today and (m is None or _days(m["as_of"], today) >= MOOD_DAYS):
            scores = sc.score_dimensions(so_far, owner["traits"], money)
            reading = sc.season_score(scores, owner["weights"])
            reading *= min(1.0, games / MOOD_FULL_GAMES)
            mood = om.next_mood(m["mood"] if m else 0.0, reading, traits["temper"])
            _set_mood(conn, league_id, team_id, sid, mood, today)
            current[team_id] = {"mood": mood, "as_of": today}
        # Check-ins, spread through the season.
        if league["state"] == "season" and games:
            count = 1 + traits["chattiness"] // 25  # 1 to 5 a season
            share = games / max(1, _season_games(conn, sid, team_id))
            due = int(share * (count + 1))
            for n in range(1, min(due, count) + 1):
                key = f"check:{sid}:{n}"
                if _has(conn, league_id, team_id, key):
                    continue
                scores = sc.score_dimensions(so_far, owner["traits"], money)
                mood = current.get(team_id, {}).get("mood", 0.0)
                body = om.checkin(
                    scores, owner["weights"], fields, _rng(sid, team_id, n), money,
                    _recent(conn, league_id, team_id),
                )  # fmt: skip
                written += _write(
                    conn, league_id, team_id, gm["id"], sid, key, "checkin", body,
                    today, om.mood_word(mood),
                )  # fmt: skip
        # Over budget.
        budget = budgets.get(team_id)
        weights = owners.clean_weights(owner["weights"])
        if (
            budget
            and weights["profit"] >= 40
            and contracts.payroll(team_id, year) > budget
            and not _has(conn, league_id, team_id, f"over:{sid}")
        ):
            body = om.over_budget(fields, _rng(sid, team_id, "over"))
            written += _write(
                conn, league_id, team_id, gm["id"], sid, f"over:{sid}", "budget",
                body, today, None,
            )  # fmt: skip
        written += _trade_reactions(
            conn, league_id, sid, team_id, gm, owner, fields, today
        )
    return written


def _trade_reactions(
    conn, league_id, season_id, team_id, gm, owner, fields, today
) -> int:
    """A word on each accepted trade this season that touches something the
    owner cares about a lot: an icon gone, more churn, a star in."""
    w = owners.clean_weights(owner["weights"])
    written = 0
    for t in conn.execute(
        """SELECT o.id,
                  EXISTS (SELECT 1 FROM trade_offer_items i JOIN all_stars a
                          ON a.player_id = i.player_id AND a.team_id = i.from_team_id
                          WHERE i.offer_id = o.id AND i.from_team_id = %s) AS icon_out,
                  EXISTS (SELECT 1 FROM trade_offer_items i JOIN all_stars a
                          ON a.player_id = i.player_id
                          WHERE i.offer_id = o.id AND i.from_team_id <> %s) AS star_in
           FROM trade_offers o
           WHERE o.season_id = %s AND o.status = 'accepted'
             AND %s IN (o.from_team_id, o.to_team_id)
           ORDER BY o.decided_at""",
        (team_id, team_id, season_id, team_id),
    ).fetchall():
        key = f"trade:{t['id']}"
        if _has(conn, league_id, team_id, key):
            continue
        what = None
        if t["icon_out"] and w["icons"] >= owners.STRONG:
            what = "icons"
        elif t["star_in"] and w["stars"] >= owners.STRONG:
            what = "stars"
        elif w["stability"] >= owners.STRONG:
            what = "stability"
        if what:
            body = om.trade_reaction(what, fields, _rng(t["id"], team_id))
            written += _write(
                conn, league_id, team_id, gm["id"], season_id, key, "trade", body,
                today, None,
            )  # fmt: skip
    return written


def review(conn, league_id: str, season_id: str, today: str | None = None) -> int:
    """The end-of-season review message, from the stored season review."""
    league = _league(conn, league_id)
    if not league:
        return 0
    money = get_mode(league["mode"]).budgets
    by_team = owner_service.ensure(conn, league_id)
    gms = _gms(conn, league_id)
    names = _team_names(conn, by_team)
    written = 0
    for r in conn.execute(
        """SELECT g.team_id, e.gm_id, e.score, e.job_security, e.detail
           FROM gm_season_evaluations e JOIN gms g ON g.id = e.gm_id
           WHERE e.season_id = %s AND g.league_id = %s AND e.job_security IS NOT NULL""",
        (season_id, league_id),
    ).fetchall():
        owner = by_team.get(r["team_id"])
        gm = gms.get(r["team_id"])
        if not owner or not gm:
            continue
        security = r["job_security"]
        band = (
            "warned" if security < sc.HOT_SEAT else "fine" if security < 60 else "safe"
        )
        fields = _fields(owner, gm, names, None)
        scores = (r["detail"] or {}).get("scores", {})
        body = om.review(
            scores,
            owner["weights"],
            fields,
            band,
            _rng(season_id, r["team_id"], "rv"),
            money,
        )
        _set_mood(conn, league_id, r["team_id"], season_id, r["score"], today)
        written += _write(
            conn, league_id, r["team_id"], r["gm_id"], season_id, f"review:{season_id}",
            "review", body, today, om.mood_word(r["score"]),
        )  # fmt: skip
    return written


def office(conn, league_id: str, team_id: str, gm_id: str) -> dict:
    """What the GM sees in the owner's office: the mood word and their
    messages, newest first. Marks them seen."""
    season = _season(conn, league_id)
    mood = None
    if season:
        m = moods(conn, league_id, season["id"]).get(team_id)
        if m:
            mood = om.mood_word(m["mood"])
    rows = conn.execute(
        """SELECT m.id, m.kind, m.body, m.created_on, m.mood, m.seen_at, s.year
           FROM owner_messages m JOIN seasons s ON s.id = m.season_id
           WHERE m.league_id = %s AND m.team_id = %s AND m.gm_id = %s
           ORDER BY m.id DESC LIMIT 60""",
        (league_id, team_id, gm_id),
    ).fetchall()
    conn.execute(
        """UPDATE owner_messages SET seen_at = NOW()
           WHERE league_id = %s AND team_id = %s AND gm_id = %s AND seen_at IS NULL""",
        (league_id, team_id, gm_id),
    )
    return {"mood": mood, "messages": [dict(r) for r in rows]}


def unseen(conn, gm_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM owner_messages WHERE gm_id = %s AND seen_at IS NULL",
        (gm_id,),
    ).fetchone()
    return int(row["n"])


def _played(conn, season_id: str) -> dict[str, int]:
    rows = conn.execute(
        """SELECT tgs.team_id, COUNT(*) AS n FROM team_game_stats tgs
           JOIN games g ON g.id = tgs.game_id
           WHERE g.season_id = %s AND g.completed = 1 AND g.series_id IS NULL
           GROUP BY tgs.team_id""",
        (season_id,),
    ).fetchall()
    return {r["team_id"]: int(r["n"]) for r in rows}


def _season_games(conn, season_id: str, team_id: str) -> int:
    row = conn.execute(
        """SELECT COUNT(*) AS n FROM games WHERE season_id = %s AND series_id IS NULL
             AND %s IN (home_team_id, away_team_id)""",
        (season_id, team_id),
    ).fetchone()
    return int(row["n"])


def _days(a: str, b: str) -> int:
    try:
        return (date.fromisoformat(str(b)[:10]) - date.fromisoformat(str(a)[:10])).days
    except ValueError:
        return MOOD_DAYS
