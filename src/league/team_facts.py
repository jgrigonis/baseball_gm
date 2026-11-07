# src/league/team_facts.py
"""
What the UI says about a team's city: its market size and climate from the
team pool (src/league/team_pool.py), in the words players and the Budget tab
use. The League page's Teams card, the Meet your team chips and the lobby's
team picker show them.
"""

from __future__ import annotations

from src.league import finances, team_pool

# The climate as the UI names it. "Temperate" reads as "Mild", the word
# players use when they wish they played somewhere else.
CLIMATE_NAMES = {
    team_pool.TROPICAL: "Tropical",
    team_pool.DESERT: "Desert",
    team_pool.WARM: "Warm",
    team_pool.TEMPERATE: "Mild",
    team_pool.COLD: "Cold",
}
# Hottest first, so the Teams card sorts climates hot to cold.
CLIMATE_ORDER = {c: i for i, c in enumerate(team_pool.CLIMATES)}


def facts(city: str, mascot: str) -> dict | None:
    """The team's region, market and climate, or None for a team that isn't
    in the pool."""
    pool = team_pool.get(city, mascot) or team_pool.by_city(city)
    if not pool:
        return None
    return {
        "region": pool.region,
        "market": pool.market,
        "market_name": finances.MARKET_NAMES.get(pool.market, "Mid-size"),
        "market_mult": finances.market_mult(pool.market),
        "climate": pool.climate,
        "climate_name": CLIMATE_NAMES.get(pool.climate, pool.climate.title()),
        "climate_order": CLIMATE_ORDER.get(pool.climate, 0),
    }


def short(city: str, mascot: str) -> str:
    """ "Big · Cold": what the lobby's team picker adds after a name."""
    f = facts(city, mascot)
    return f"{f['market_name']} · {f['climate_name']}" if f else ""


def market_rank(market: int, markets: list[int]) -> tuple[int, bool]:
    """Where a market ranks among the league's (1 = biggest), and whether
    another team shares it."""
    rank = 1 + sum(1 for m in markets if m > market)
    return rank, markets.count(market) > 1


def league_teams(db, league_id: str, my_team_id: str | None = None) -> list[dict]:
    """Every team in the league with its city facts, biggest market first."""
    # Every team has a GM, person or AI, so the GMs list the league's teams.
    rows = db.execute(
        """SELECT DISTINCT t.id, t.city, t.mascot
           FROM gms g JOIN teams t ON t.id = g.team_id
           WHERE g.league_id = %s AND g.fired_at IS NULL""",
        (league_id,),
    ).fetchall()
    out = []
    for r in rows:
        f = facts(r["city"], r["mascot"])
        if not f:
            continue
        out.append(
            {
                "id": r["id"],
                "city": r["city"],
                "mascot": r["mascot"],
                "mine": r["id"] == my_team_id,
                **f,
            }
        )
    out.sort(key=lambda t: (-t["market"], t["city"], t["mascot"]))
    return out


def team_card(db, league_id: str, team_id: str) -> dict | None:
    """One team's facts plus where its market ranks in the league: the Meet
    your team chips."""
    teams = league_teams(db, league_id, team_id)
    mine = next((t for t in teams if t["mine"]), None)
    if not mine:
        return None
    rank, tied = market_rank(mine["market"], [t["market"] for t in teams])
    place = f"{'tied ' if tied else ''}{_ordinal(rank)} of {len(teams)}"
    return {**mine, "market_rank": rank, "market_tied": tied, "market_place": place}


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"
