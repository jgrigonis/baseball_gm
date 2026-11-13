# src/api/view_models/profile_sections.py
#
# The GM profile's lower sections (plans/gm-profile-page.md, phase 3): draft
# record, trades, GM style and timeline; and phase 4, rivals.
#
# The career rows (gm_career_seasons) outlive their leagues; draft picks,
# trade details and settings are read from the leagues the person still
# runs a team in, so a league they left or that was deleted drops out of
# those lists. Rivals come from gm_head_to_head, which outlives them too.
# Tutorial leagues never count.

from __future__ import annotations

from collections import Counter

from src.db.repositories.career_repo import CareerRepository
from src.player.positions import display_position

PITCHER_POSITIONS = ("p", "sp", "rp")
# About 39% of a draft class are pitchers (draft_generator.PITCHER_SHARE).
PITCHER_HEAVY = 0.5
PITCHER_LIGHT = 0.28
# Draft classes are 18-22, about 20 on average (draft_generator.AGE_DISTRIBUTION).
YOUNG_PICKS = 19.6
OLD_PICKS = 20.4

WIN_NOW = ("all-in", "contending")
BUILDING = ("rebuilding", "ramping-up")

LINEUP_STYLE = {
    "traditional": "Traditional",
    "analytics": "Analytics",
    "speed-first": "Speed first",
    "power-first": "Power first",
    "defensive": "Defensive",
}
BASERUNNING = {
    "very-conservative": "Very careful on the bases",
    "conservative": "Careful on the bases",
    "standard": "Standard baserunning",
    "aggressive": "Aggressive on the bases",
    "very-aggressive": "Very aggressive on the bases",
}
STARTER_USAGE = {u: f"{u}-pitch leash" for u in ("115", "105", "95", "85", "75")}
CLOSER_USAGE = {
    "saves-only": "closer for saves",
    "high-leverage": "closer in big spots",
    "best-available": "best arm available",
}

BEST_PICKS_SHOWN = 5
TRADES_SHOWN = 5
TIMELINE_SHOWN = 12
RIVALS_SHOWN = 8


def sections(db, user_id: str, seasons: list[dict]) -> dict:
    picks = _picks(db, user_id)
    trades = _trades(db, user_id)
    return {
        "draft": _draft(picks),
        "trades": _trade_summary(db, user_id, seasons, trades),
        "style": _style(db, user_id, seasons, picks),
        "timeline": _timeline(seasons, trades),
        "rivals": _rivals(db, user_id),
    }


# ── Draft record ──────────────────────────────────────────────────────────────


def _picks(db, user_id: str) -> list[dict]:
    rows = db.execute(
        """SELECT dp.pick_number, dp.round, dp.player_id, pl.first_name, pl.last_name,
                  pl.position, s.year AS draft_year, t.city, t.mascot,
                  l.name AS league_name, ps.age AS age_now,
                  (SELECT COUNT(*) FROM all_stars a
                   WHERE a.player_id = dp.player_id) AS all_stars,
                  (SELECT MAX(s2.year) FROM league_seasons ls2
                   JOIN seasons s2 ON s2.id = ls2.season_id
                   WHERE ls2.league_id = l.id) AS league_year
           FROM draft_picks dp
           JOIN gms g ON g.id = dp.gm_id
           JOIN leagues l ON l.id = g.league_id AND NOT l.is_practice
           JOIN drafts d ON d.id = dp.draft_id
           JOIN seasons s ON s.id = d.season_id
           JOIN players pl ON pl.id = dp.player_id
           JOIN teams t ON t.id = dp.team_id
           LEFT JOIN player_skills ps ON ps.player_id = dp.player_id
           WHERE g.user_id = %s""",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _draft(picks: list[dict]) -> dict | None:
    if not picks:
        return None
    stars = [p for p in picks if p["all_stars"]]
    stars.sort(key=lambda p: (-p["all_stars"], p["round"], p["pick_number"]))
    best = stars[:BEST_PICKS_SHOWN]
    if not best:
        # Nobody's made an All-Star team yet: their highest picks.
        best = sorted(picks, key=lambda p: (p["pick_number"], -p["draft_year"]))[:3]
    return {
        "picks": len(picks),
        "all_stars": len(stars),
        "best": [
            {
                "name": f"{p['first_name']} {p['last_name']}",
                "position": display_position(p["position"]),
                "when": f"{p['draft_year']} · R{p['round']} #{p['pick_number']}",
                "city": p["city"],
                "mascot": p["mascot"],
                "became": _all_star_label(p["all_stars"]),
            }
            for p in best
        ],
        "any_stars": bool(stars),
    }


def _all_star_label(n: int) -> str:
    if not n:
        return "No All-Star team yet"
    return "All-Star" if n == 1 else f"{n}× All-Star"


# ── Trades ────────────────────────────────────────────────────────────────────


def _trades(db, user_id: str) -> list[dict]:
    """Accepted trades the person's teams made while they ran them, newest
    first, each as {year, partner, sent, got}."""
    offers = db.execute(
        """SELECT o.id, s.year, g.team_id AS mine,
                  CASE WHEN o.from_team_id = g.team_id THEN o.to_team_id
                       ELSE o.from_team_id END AS partner_id,
                  l.name AS league_name
           FROM trade_offers o
           JOIN gms g ON g.league_id = o.league_id
                     AND g.team_id IN (o.from_team_id, o.to_team_id)
           JOIN leagues l ON l.id = o.league_id AND NOT l.is_practice
           JOIN seasons s ON s.id = o.season_id
           WHERE g.user_id = %s AND o.status = 'accepted'
           ORDER BY o.decided_at DESC NULLS LAST, o.created_at DESC""",
        (user_id,),
    ).fetchall()
    if not offers:
        return []
    ids = [o["id"] for o in offers]
    players = db.execute(
        """SELECT i.offer_id, i.from_team_id, p.first_name, p.last_name
           FROM trade_offer_items i JOIN players p ON p.id = i.player_id
           WHERE i.offer_id = ANY(%s) ORDER BY p.last_name""",
        (ids,),
    ).fetchall()
    picks = db.execute(
        """SELECT k.offer_id, k.from_team_id, k.draft_year, k.round, t.city
           FROM trade_offer_picks k JOIN teams t ON t.id = k.original_team_id
           WHERE k.offer_id = ANY(%s) ORDER BY k.draft_year, k.round""",
        (ids,),
    ).fetchall()
    teams = {
        r["id"]: dict(r)
        for r in db.execute(
            "SELECT id, city, mascot FROM teams WHERE id = ANY(%s)",
            ([o["partner_id"] for o in offers],),
        ).fetchall()
    }
    out = []
    for o in offers:
        sent, got = [], []
        for p in players:
            if p["offer_id"] == o["id"]:
                side = sent if p["from_team_id"] == o["mine"] else got
                side.append(f"{p['first_name']} {p['last_name']}")
        for k in picks:
            if k["offer_id"] == o["id"]:
                side = sent if k["from_team_id"] == o["mine"] else got
                side.append(f"{k['city']}'s {k['draft_year']} round {k['round']} pick")
        partner = teams.get(o["partner_id"], {"city": "?", "mascot": ""})
        out.append(
            {
                "year": o["year"],
                "league_name": o["league_name"],
                "city": partner["city"],
                "mascot": partner["mascot"],
                "sent": _and(sent),
                "got": _and(got),
            }
        )
    return out


def _and(items: list[str]) -> str:
    if not items:
        return "nothing"
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _trade_summary(
    db, user_id: str, seasons: list[dict], trades: list[dict]
) -> dict | None:
    accepted = sum(s["trades"] for s in seasons)
    offered = db.execute(
        """SELECT COUNT(*) AS n FROM trade_offers o
           JOIN gms g ON g.id = o.from_gm_id
           JOIN leagues l ON l.id = g.league_id AND NOT l.is_practice
           WHERE g.user_id = %s""",
        (user_id,),
    ).fetchone()["n"]
    if not accepted and not offered and not trades:
        return None
    return {
        "accepted": max(accepted, len(trades)),
        "offered": offered,
        "recent": trades[:TRADES_SHOWN],
    }


# ── GM style ──────────────────────────────────────────────────────────────────


def _style(db, user_id: str, seasons: list[dict], picks: list[dict]) -> list[dict]:
    """How they tend to run a team, from what they did: (label, word, why)."""
    rows = []

    states = [s["front_office"] for s in seasons if s.get("front_office")]
    if states:
        win_now = sum(1 for s in states if s in WIN_NOW)
        building = sum(1 for s in states if s in BUILDING)
        n = len(states)
        seasons_word = "season" if n == 1 else "seasons"
        if win_now * 2 > n:
            rows.append(
                (
                    "Front office",
                    "Win-now",
                    f"Contending or all-in {win_now} of {n} {seasons_word}",
                )
            )
        elif building * 2 > n:
            rows.append(
                (
                    "Front office",
                    "Building",
                    f"Rebuilding or ramping up {building} of {n} {seasons_word}",
                )
            )
        else:
            top = Counter(states).most_common(1)[0][0]
            rows.append(
                ("Front office", "In between", f"Most often {top.replace('-', ' ')}")
            )

    early = [p for p in picks if p["round"] <= 3]
    if early:
        share = sum(
            1 for p in early if (p["position"] or "") in PITCHER_POSITIONS
        ) / len(early)
        word = (
            "Pitching first" if share >= PITCHER_HEAVY
            else "Bats first" if share <= PITCHER_LIGHT
            else "Balanced"
        )  # fmt: skip
        rows.append(
            ("Draft", word, f"{round(share * 100)}% of round 1-3 picks were pitchers")
        )

    ages = [
        p["age_now"] - (p["league_year"] - p["draft_year"])
        for p in picks
        if p["age_now"] is not None and p["league_year"] is not None
    ]
    if ages:
        avg = sum(ages) / len(ages)
        word = (
            "Young upside"
            if avg < YOUNG_PICKS
            else "Ready sooner"
            if avg > OLD_PICKS
            else "Balanced"
        )
        rows.append(("Draft age", word, f"Average age when picked: {avg:.1f}"))

    if seasons:
        per_season = sum(s["trades"] for s in seasons) / len(seasons)
        word = (
            "Active"
            if per_season >= 1.5
            else "Now and then"
            if per_season >= 0.5
            else "Rarely"
        )
        rows.append(("Trades", word, f"{per_season:.1f} trades a season"))

    prof = db.execute(
        """SELECT p.* FROM gm_profiles p JOIN gms g ON g.id = p.gm_id
           JOIN leagues l ON l.id = g.league_id AND NOT l.is_practice
           WHERE g.user_id = %s ORDER BY g.created_at DESC LIMIT 1""",
        (user_id,),
    ).fetchone()
    if prof:
        rows.append(
            (
                "Lineups",
                LINEUP_STYLE.get(prof["lineup_style"], prof["lineup_style"]),
                BASERUNNING.get(prof["baserunning"], ""),
            )
        )
        rows.append((
            "Pitching",
            STARTER_USAGE.get(prof["starter_usage"], prof["starter_usage"]),
            f"{prof['rotation_size']}-man rotation, {CLOSER_USAGE.get(prof['closer_usage'], '')}",
        ))  # fmt: skip

    return [{"label": a, "word": b, "why": c} for a, b, c in rows]


# ── Timeline ──────────────────────────────────────────────────────────────────


# ── Rivals ────────────────────────────────────────────────────────────────────


def _rivals(db, user_id: str) -> list[dict]:
    """Their record against each other person they've played, most games
    first, from gm_head_to_head (so it outlives the leagues). The team is the
    one the rival ran most recently, and the note is their latest playoff
    meeting."""
    from src.api.view_models.profile import pct  # profile imports this module

    by_rival: dict[str, dict] = {}
    for r in CareerRepository(db).head_to_head_for(user_id):  # newest first
        rival = by_rival.get(r["opponent_id"])
        if rival is None:
            rival = by_rival[r["opponent_id"]] = {
                "username": r["opponent_username"],
                "name": r["opponent_name"] or r["opponent_username"] or "A GM",
                "city": r["opponent_city"],
                "mascot": r["opponent_mascot"],
                "wins": 0,
                "losses": 0,
                "note": None,
            }
        rival["wins"] += r["wins"]
        rival["losses"] += r["losses"]
        if rival["note"] is None and r["series_round"]:
            where = f"the {r['season_year']} {r['series_round']}"
            rival["note"] = (
                f"Beat them in {where}"
                if r["series_won"]
                else f"Lost to them in {where}"
            )
    rows = sorted(by_rival.values(), key=lambda v: -(v["wins"] + v["losses"]))
    for v in rows:
        v["pct"] = pct(v["wins"], v["losses"])
    return rows[:RIVALS_SHOWN]


def _timeline(seasons: list[dict], trades: list[dict]) -> list[dict]:
    """Milestones, newest first: titles and deep playoff runs, division
    titles, 100-win seasons and sweeps, and trades."""
    events = []  # (year, order within the year, item)

    def add(year, order, icon, text, league):
        item = {"year": year, "icon": icon, "text": text, "league_name": league}
        events.append((year, order, item))

    for s in seasons:
        team = f"{s['team_city']} {s['team_mascot']}"
        y, lg = s["season_year"], s["league_name"]
        result = s["playoff_result"]
        if result == "Champion":
            add(y, 0, "🏆", f"Won the title with the {team}", lg)
        elif result == "Finals":
            add(y, 1, "🥈", f"Reached the Finals with the {team}", lg)
        if s["sweeps"]:
            n = s["sweeps"]
            add(
                y,
                2,
                "🧹",
                "Swept a playoff series" if n == 1 else f"Swept {n} playoff series",
                lg,
            )
        if s["division_title"]:
            add(y, 3, "🚩", f"Won the division ({s['wins']}-{s['losses']})", lg)
        if s["wins"] >= 100:
            add(y, 4, "💯", f"A {s['wins']}-win season", lg)
    for t in trades:
        add(
            t["year"], 5, "🔁",
            f"Traded {t['sent']} to {t['city']} for {t['got']}",
            t["league_name"],
        )  # fmt: skip
    events.sort(key=lambda e: (-e[0], e[1]))
    return [e[2] for e in events[:TIMELINE_SHOWN]]
