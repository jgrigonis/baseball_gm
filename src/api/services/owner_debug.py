# src/api/services/owner_debug.py
#
# Admin only: how a team's owner reads the season, number by number (Josh,
# 2026-11-11: "Do we have debug details on owner happiness somewhere?").
# The same scoring the weekly mood and the check-ins use
# (owner_office.catch_up), laid out for the Owner tab: each dimension's
# score, its weight, what it was read from, the mood and the reading it's
# moving toward, what moved it this season, and job security. GMs never see
# any of this (plans/owners.md: numbers are admin-only).

from __future__ import annotations

from dataclasses import replace

from src.api.services import owner_office as oo
from src.api.services import owner_review
from src.api.services import owners as owner_service
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.contract_repo import ContractRepository
from src.league import owner_messages as om
from src.league import owner_scoring as sc
from src.league import owners
from src.league.league_modes import get_mode
from src.player.contracts import format_salary

# Owner messages that move the mood the moment they're written (the rest
# only say what the weekly reading already counts).
EVENT_KINDS = ("trade", "release", "streak", "veto", "budget")


def _pct(x: float) -> str:
    """.554, -.054: win % style."""
    text = f"{x:.3f}"
    return text.replace("0.", ".", 1) if abs(x) < 1 else text


def _money(n) -> str:
    if n is None:
        return "—"
    return ("-" if n < 0 else "") + format_salary(abs(int(n)))


def _why(key: str, s: sc.TeamSeason, traits: dict, state: str) -> str:
    """What the dimension's score was read from, in short."""
    ambition = traits["ambition"]
    if key == "wins":
        target = sc.win_target(s.rank_before, ambition)
        return (
            f"{s.wins}-{s.losses} ({_pct(s.win_pct)}) vs target {_pct(target)}"
            f" from roster rank {s.rank_before:.2f} (0 best) and ambition"
            f" {ambition}; {_pct(sc.WIN_SCALE)} off = ±1"
        )
    if key == "postseason":
        expected = sc.expects_playoffs(s.rank_before, ambition)
        exp = "expects playoffs" if expected else "doesn't expect playoffs"
        if state == "season":
            return f"Not judged until the playoffs ({exp})"
        if s.champion:
            return "Won it all"
        if s.made_playoffs:
            return f"Made playoffs, won {s.rounds_won} round(s); {exp}"
        return f"Missed playoffs; {exp}"
    if key == "profit":
        if s.profit is None or not s.revenue:
            return "No money numbers this season"
        par = (
            f", par {_money(s.profit_par)}"
            if s.profit_par is not None
            else f", target margin {sc.PROFIT_TARGET:.0%}"
        )
        return (
            f"Profit {_money(s.profit)} on revenue {_money(s.revenue)}{par};"
            f" ±{sc.PROFIT_SCALE:.0%} of revenue = ±1"
        )
    if key == "attendance":
        if s.crowd_score is not None:
            return f"Home crowds read {s.crowd_score:+.2f}"
        if s.fans_after is not None:
            return f"Fan interest {s.fans_after} (50 = 0, ±30 = ±1)"
        return "No money numbers this season"
    if key == "fans":
        if s.fans_after is None:
            return "No money numbers this season"
        before = s.fans_before if s.fans_before is not None else 50
        return f"Fan interest {before} → {s.fans_after} (±8 = ±1)"
    if key == "future":
        return (
            f"Rank in two years {s.rank_future:.2f}, farm rank {s.farm_rank:.2f}"
            " (0 best, .5 = middle)"
        )
    if key == "homegrown":
        mark = 0.3 if s.league_homegrown is None else s.league_homegrown
        return (
            f"{s.homegrown_players} of {s.roster_players} drafted here"
            f" ({s.homegrown_share:.0%}) vs league {mark:.0%}; ±25 pts = ±1"
        )
    if key == "stars":
        mark = 1.5 if s.league_star_points is None else s.league_star_points
        return (
            f"{s.all_stars} All-Stars + {s.award_winners} awards = "
            f"{s.star_points:.1f} pts vs league {mark:.1f}; ±2.5 = ±1"
        )
    if key == "icons":
        return f"{s.icons_lost} icon(s) lost: 0.1 − 0.6 each"
    if key == "stability":
        return (
            f"{s.trades} trade(s), {s.releases} B- or better release(s):"
            " 0.25 − 0.2 a trade − 0.1 a release"
        )
    if key == "rivalry":
        games = s.rival_wins + s.rival_losses
        if not games:
            return "No games against the rival yet"
        return f"{s.rival_wins}-{s.rival_losses} vs rival; .700 = +1, .300 = -1"
    return ""


def explain(conn, league_id: str, team_id: str) -> dict | None:
    """Everything behind this team's owner's mood and job security, for an
    admin. None if the team has no owner."""
    league = oo._league(conn, league_id)
    season = oo._season(conn, league_id)
    by_team = owner_service.ensure(conn, league_id)
    owner = by_team.get(team_id)
    if not league or not season or not owner:
        return None
    money = get_mode(league["mode"]).budgets
    state = league["state"]
    year, sid = season["year"], season["id"]
    weights = owners.clean_weights(owner["weights"])
    traits = owners.clean_traits(owner["traits"])
    in_season = state in ("season", "playoffs")

    # The season as the owner reads it today (as owner_office.catch_up does).
    s = None
    scores: dict = {}
    if in_season:
        facts = owner_review.gather(conn, league_id, sid, year, by_team)
        s = facts.get(team_id)
    if s is not None:
        payroll = ContractRepository(conn).payroll(team_id, year)
        s = replace(s, payroll=payroll)
        p = (BudgetRepository(conn).projected(league_id, year) if money else {}).get(
            team_id
        )
        if p and s.profit is None:
            s = replace(s, revenue=p["revenue"], profit=p["profit"])
        scores = oo._in_season(s, owner["traits"], money, state)
        source = "This season so far"
    else:
        # Between seasons: last season's review, as it was stored.
        last = owner_review.security_now(conn, league_id).get(team_id)
        detail = (last or {}).get("detail") or {}
        if detail.get("facts"):
            known = set(sc.TeamSeason.__dataclass_fields__)
            s = sc.TeamSeason(
                **{k: v for k, v in detail["facts"].items() if k in known}
            )
            scores = detail.get("scores") or {}
        source = f"Last season's review ({last['year']})" if last else None

    fields = {"rival": owner.get("rival_team_id")}
    talks = set(om._speakable(owner["weights"], fields, money)[:6])
    judged = {k: v for k, v in scores.items() if v is not None and weights.get(k)}
    total_w = sum(weights[k] for k in judged) or 1
    rows = []
    for key, label, how in owners.DIMENSIONS:
        v = scores.get(key)
        share = weights[key] / total_w if key in judged else 0.0
        rows.append(
            {
                "key": key,
                "label": label,
                "weight": weights[key],
                "share": share,
                "score": v,
                "tone": om.tone(v) if v is not None else None,
                "counts": share * v if key in judged else None,
                "talks": key in talks,
                "why": _why(key, s, traits, state) if s is not None else how,
            }
        )
    rows.sort(key=lambda r: -(r["weight"]))
    reading = sc.season_score(scores, owner["weights"]) if scores else None

    games = (s.wins + s.losses) if s is not None and in_season else 0
    discount = min(1.0, games / oo.MOOD_FULL_GAMES) if in_season else 1.0
    m = oo.moods(conn, league_id, sid).get(team_id)
    mood = m["mood"] if m else oo.latest_moods(conn, league_id).get(team_id, 0.0)
    step = 0.25 + 0.55 * traits["temper"] / 100

    events = [
        dict(r)
        for r in conn.execute(
            """SELECT kind, key, body, created_on FROM owner_messages
               WHERE league_id = %s AND team_id = %s AND season_id = %s
                 AND kind = ANY(%s)
               ORDER BY id DESC LIMIT 20""",
            (league_id, team_id, sid, list(EVENT_KINDS)),
        ).fetchall()
    ]
    history = [
        dict(r)
        for r in conn.execute(
            """SELECT s.year, e.wins, e.losses, e.score, e.job_security, e.verdict,
                      e.detail->>'raw_score' AS raw_score,
                      e.detail->>'security_before' AS security_before,
                      e.detail->>'win_target' AS win_target,
                      e.detail->>'would_fire' AS would_fire,
                      g.display_name, g.is_ai
               FROM gm_season_evaluations e
               JOIN gms g ON g.id = e.gm_id
               JOIN seasons s ON s.id = e.season_id
               WHERE g.league_id = %s AND g.team_id = %s
                 AND e.job_security IS NOT NULL
               ORDER BY s.year DESC LIMIT 8""",
            (league_id, team_id),
        ).fetchall()
    ]
    rules = sc.firing_rules(owner.get("archetype"))
    return {
        "source": source,
        "state": state,
        "archetype": owner.get("archetype"),
        "traits": [
            {"label": label, "value": traits[k], "ends": (lo, hi)}
            for k, label, lo, hi in owners.TRAITS
        ],
        "rows": rows,
        "reading": reading,
        "games": games,
        "discount": discount,
        "target": reading * discount if reading is not None else None,
        "mood": mood,
        "mood_word": om.mood_word(mood),
        "mood_as_of": m["as_of"] if m else None,
        "step": step,
        "moods": [{"floor": f, "word": w} for f, w in om.MOODS],
        "events": events,
        "release_moods": oo.RELEASE_MOOD,
        "temper_factor": 0.5 + traits["temper"] / 100,
        "history": history,
        "hot_seat": sc.HOT_SEAT,
        "fire": sc.FIRE,
        "rules": rules,
        "firing_on": bool(
            conn.execute(
                "SELECT owner_firing FROM leagues WHERE id = %s", (league_id,)
            ).fetchone()["owner_firing"]
        ),
    }
