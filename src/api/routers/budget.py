# src/api/routers/budget.py
#
# The Budget tab (plans/budget.md, Q7): the GM's money this season (the
# league's cap, the owner's budget and hard limit, payroll and the luxury
# tax), the owner's bank, the front office (set once each offseason) and
# the team's money season by season. Only money: the owner's traits stay
# hidden, and front office levels are the GM's own. Not in Speed Blitz.


from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from src.api.dependencies import DB, GM, ActiveLeague, IsHTMX, User
from src.db.locks import league_lock
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.contract_repo import ContractRepository
from src.league import budget as bg
from src.league import finances as fn
from src.player.contracts import format_salary
from src.web.utils import _shell_ctx, tab_response

router = APIRouter(tags=["web"])
# When front office levels can change: between seasons, from the draft to
# Opening Day. They're locked once the season starts.
FRONT_OFFICE_STATES = ("draft", "preseason")


def _money(amount) -> str | None:
    if amount is None:
        return None
    text = format_salary(abs(int(amount)))
    return f"-{text}" if amount < 0 else text


def _times(mult: float) -> str:
    return f"\u00d7{mult:.2f}"


def _seasons(n: int) -> str:
    return f"{n} season{'' if n == 1 else 's'}"


def _broadcast_note(b: dict) -> str:
    deal = b.get("deal")
    if not deal:
        return "A local TV deal, priced from your market, fans and recent winning"
    if not b["projected"]:
        return f"Local TV deal signed in {deal['start_year']} for {_seasons(deal['years'])}"
    left = deal["left"]
    return f"Local TV deal for {_seasons(deal['years'])}, " + (
        "this is its last season" if left == 1 else f"{_seasons(left)} left"
    )


def _merch_note(b: dict, names: dict) -> str:
    sellers = b.get("sellers") or []
    hall = sum(amount for s, amount in sellers if s.hall)
    players = [(s, amount) for s, amount in sellers if not s.hall]
    parts = []
    if players:
        parts.append(
            "Top sellers: "
            + ", ".join(
                f"{names.get(s.player_id, 'a player')} {_money(amount)}"
                for s, amount in players[:3]
            )
        )
    if hall:
        parts.append(f"Hall of Famers {_money(hall)}")
    if parts:
        return "; ".join(parts)
    if b["merchandise"]:
        return "What your players' jerseys and gear sold"
    return "Players graded B+ or better sell jerseys, stars far more"


def _sponsor_note(b: dict) -> str:
    deal = b.get("sponsor_deal")
    if not deal:
        return "Sponsors pay a steady deal, or more the better you do"
    name = fn.SPONSOR_NAMES.get(deal["kind"], "Steady")
    if deal["kind"] != "incentive":
        return f"{name} sponsor deal: the same whatever happens"
    if not b["projected"] or "base" not in deal:
        return f"{name} sponsor deal: paid on how the season went"
    parts = [f"{_money(deal['base'])} up front"]
    if deal["wins"]:
        parts.append(f"{_money(deal['wins'])} for winning")
    if deal["playoffs"]:
        parts.append(f"{_money(deal['playoffs'])} for the playoffs")
    if deal["rounds"]:
        n = deal["rounds"]
        parts.append(f"{_money(deal['rounds'])} for {n} series won")
    return f"{name} sponsor deal so far: " + ", ".join(parts)


def _popularity_note(b: dict) -> str:
    """What fan interest is, what it is now, what each point over the line
    is worth and how to raise it (fn.popularity_money)."""
    fans, line = b["fans"], b["popularity_from"]
    point, top = b.get("popularity_point"), b.get("popularity_top")
    text = (
        "Fan interest, how keen your fans are on a 0 to 100 scale,"
        f" came into the season at {fans}. "
    )
    over = fans - line
    if over > 0:
        text += f"That's {over} point{'' if over == 1 else 's'} over {line}"
    else:
        text += f"Only points over {line} pay"
    if point:
        text += f", each worth {_money(point)}"
    if top:
        text += f", up to {_money(top)} at {b['fans_max']}"
    return (
        text + ". Winning, the playoffs, a title, All-Stars, cheaper tickets,"
        " marketing and ballpark upgrades raise it after each season."
    )


def _books_view(b: dict, names: dict | None = None) -> dict:
    """One season's money in and out (BudgetRepository.books), as text."""
    names = names or {}
    games = b["home_playoff_games"]
    money_in = [
        {
            "label": "Regular season",
            "amount": _money(b["revenue"]),
            "note": (
                f"{_money(b['base'])} league base"
                f" {_times(b['market_mult'])} {b['market_name'].lower()} market"
                f" {_times(b['fan_mult'])} fan interest {b['fans']}"
            ),
        },
        {
            "label": "Ticket prices",
            "amount": _money(b["tickets"]) if b["tickets"] else None,
            "note": f"{b['ticket_name']} ({b['ticket_price']} of 10)"
            + (f": {b['ticket_pct']:+g}% at the gate" if b["ticket_pct"] else ""),
            "bad": b["tickets"] < 0,
        },
        {
            "label": "Crowds",
            "amount": (
                (f"+{_money(b['crowds'])}" if b["crowds"] > 0 else _money(b["crowds"]))
                if b["crowds"]
                else None
            ),
            "note": (
                f"{round(fn.GATE_SHARE * 100)}% of the gate follows the crowds:"
                + (" bigger" if b["crowds"] > 0 else " smaller")
                + " than your fans were expected to bring"
                + (" so far" if b["projected"] else "")
                if b["crowds"]
                else f"{round(fn.GATE_SHARE * 100)}% of the gate follows the crowds,"
                " against what your fans are expected to bring"
            ),
            "bad": b["crowds"] < 0,
        },
        {
            "label": "Playoff gate",
            "amount": _money(b["playoff_gate"]) if b["playoff_gate"] else None,
            "note": (
                f"{games} home playoff game{'' if games == 1 else 's'}"
                f"{' so far' if b['projected'] else ''}"
                f" at {_money(b['gate_per_game'])} each"
                if games
                else f"{_money(b['gate_per_game'])} for each home playoff game"
            ),
        },
        {
            "label": "Popularity",
            "amount": _money(b["popularity"]) if b["popularity"] else None,
            "note": _popularity_note(b),
        },
        {
            "label": "Broadcast deal",
            "amount": _money(b["broadcast"]) if b["broadcast"] else None,
            "note": _broadcast_note(b),
        },
        {
            "label": "Merchandise",
            "amount": _money(b["merchandise"]) if b["merchandise"] else None,
            "note": _merch_note(b, names),
        },
        {
            "label": "Sponsors",
            "amount": _money(b["sponsor"]) if b["sponsor"] else None,
            "note": _sponsor_note(b),
        },
        {
            "label": "Ballpark",
            "amount": _money(b["ballpark"]) if b["ballpark"] else None,
            "note": (
                "What your ballpark upgrades earn"
                if b["ballpark"]
                else "Upgrades your owner pays for earn money every season"
            ),
        },
        {
            "label": "Luxury tax share",
            "amount": _money(b["tax_share"]) if b["tax_share"] else None,
            "note": (
                "Your cut of the tax paid by teams over the cap"
                if b["tax_share"]
                else "Paid to teams under the cap when someone goes over"
            ),
        },
        {
            "label": "League farm help",
            "amount": _money(b["farm_help"]) if b["farm_help"] else None,
            "note": "The league covers an average farm's salaries",
        },
    ]
    money_out = [
        {"label": "Payroll", "amount": _money(b["payroll"]),
         "note": "Guaranteed salaries plus dead money"},
        {"label": "Front office", "amount": _money(b["front_office"]),
         "note": "Coaching, facilities, analytics and marketing"},
        {"label": "Minor leagues", "amount": _money(b["minor_league"]) if b["minor_league"] else None,
         "note": "Salaries of players off the 40-man"},
        {"label": "Luxury tax", "amount": _money(b["luxury_tax"]) if b["luxury_tax"] else None,
         "note": f"{round(bg.LUXURY_TAX_RATE * 100)}% of payroll over the cap", "bad": bool(b["luxury_tax"])},
        {"label": "Fixed costs", "amount": _money(b["costs"]),
         "note": "Ballpark, travel and staff, the same for every team"},
    ]  # fmt: skip
    if b["other"]:
        money_out.append(
            {"label": "Other costs", "amount": _money(b["other"]), "note": ""}
        )
    return {
        "year": b["year"],
        "projected": b["projected"],
        "money_in": money_in,
        "money_out": money_out,
        "total_in": _money(b["total_in"]),
        "total_out": _money(b["total_out"]),
        "profit": _money(b["profit"]),
        "loss": b["profit"] < 0,
    }


def _past_seasons(past: list[dict], books: list[dict]) -> list[dict]:
    """The Past seasons table: each finished season's money in a row that
    adds up. Revenue less payroll, plus or minus the luxury tax, less the
    front office, minor leagues and the league's fixed costs (net of its
    farm help) is the profit; the profit less ballpark payments is the
    change in the owner's bank. Revenue opens its breakdown."""
    closed = {b["year"]: b for b in books if not b["projected"]}
    rows = []
    for r in past:
        b = closed.get(r["year"])
        if r["profit"] is None or b is None:
            continue
        revenue = b["total_in"] - b["tax_share"] - b["farm_help"]
        tax = b["tax_share"] - b["luxury_tax"]
        fixed = b["costs"] - b["farm_help"]
        park = r["bank_spent"] or 0
        lines = [
            ("Regular season tickets", b["revenue"] + b["tickets"] + b["crowds"]),
            ("Playoff gate", b["playoff_gate"]),
            ("Popularity", b["popularity"]),
            ("Broadcast deal", b["broadcast"]),
            ("Merchandise", b["merchandise"]),
            ("Sponsors", b["sponsor"]),
            ("Ballpark upgrades", b["ballpark"]),
        ]
        rows.append(
            {
                "year": r["year"],
                "revenue": _money(revenue),
                "revenue_lines": [
                    {"label": label, "amount": _money(amount)}
                    for label, amount in lines
                    if amount
                ],
                "payroll": _money(b["payroll"]),
                "tax": (f"+{_money(tax)}" if tax > 0 else _money(tax)) if tax else None,
                "tax_paid": tax < 0,
                "front_office": _money(b["front_office"]),
                "minor_league": _money(b["minor_league"])
                if b["minor_league"]
                else None,
                "fixed": _money(fixed),
                "other": _money(b["other"]) if b["other"] else None,
                "profit": _money(b["profit"]),
                "loss": b["profit"] < 0,
                "gain": b["profit"] > 0,
                "park": _money(park) if park else None,
                "fans": r["fans_after"],
                "crowd": (
                    f"{round(r['attendance'] / r['crowd_games']):,}"
                    if r.get("crowd_games")
                    else None
                ),
                "crowd_full": (
                    round(100 * r["attendance"] / (r["crowd_games"] * r["capacity"]))
                    if r.get("crowd_games") and r.get("capacity")
                    else None
                ),
                "bank": _money(r["bank_after"]),
            }
        )
    return rows


@router.get("/leagues/{league_id}/budget", response_class=HTMLResponse)
def budget_tab(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
):
    return _render(request, htmx, league_id, db, user, gm)


@router.post("/leagues/{league_id}/budget/front-office", response_class=HTMLResponse)
def set_front_office(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
    _active: ActiveLeague,
    department: str = Form(...),
    level: int = Form(...),
):
    """Fund one department at a level. Only between seasons, and the owner
    won't pay for a raise above Standard past their hard limit."""
    team_id = gm.get("team_id")
    error = None
    with league_lock(db, league_id):
        league = LeagueRepository(db).get_by_id(league_id)
        budgets = BudgetRepository(db)
        year = ContractRepository(db).current_year(league_id)
        levels = budgets.levels(league_id, team_id, year) if year else {}
        if not levels or department not in bg.DEPARTMENT_KEYS:
            error = "This league has no front office budget."
        elif league["state"] not in FRONT_OFFICE_STATES:
            error = "The front office is set between seasons, from the draft to Opening Day."
        else:
            # Standard or less is always allowed, even past the owner's hard
            # limit (Josh, 2026-11-09); only funding above Standard has to
            # fit inside it.
            cap = budgets.cap(league_id, year)
            added = bg.level_cost(cap, level) - bg.level_cost(cap, levels[department])
            if bg.clean_level(level) > bg.STANDARD:
                error = budgets.refusal(league_id, team_id, year, added, payroll=False)
            if not error:
                budgets.set_level(league_id, team_id, year, department, level)
        db.commit()
    return _render(request, htmx, league_id, db, user, gm, error, saved=not error)


@router.post("/leagues/{league_id}/budget/tickets", response_class=HTMLResponse)
def set_tickets(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
    _active: ActiveLeague,
    level: int = Form(...),
):
    """Set ticket prices for the season. Only between seasons, like the
    front office."""
    team_id = gm.get("team_id")
    error = None
    with league_lock(db, league_id):
        league = LeagueRepository(db).get_by_id(league_id)
        budgets = BudgetRepository(db)
        year = ContractRepository(db).current_year(league_id)
        if not year or budgets.ticket_price(league_id, team_id, year) is None:
            error = "This league has no ticket prices."
        elif league["state"] not in FRONT_OFFICE_STATES:
            error = (
                "Ticket prices are set between seasons, from the draft to Opening Day."
            )
        else:
            budgets.set_ticket_price(league_id, team_id, year, level)
        db.commit()
    return _render(
        request, htmx, league_id, db, user, gm,
        ticket_error=error, ticket_saved=not error,
    )  # fmt: skip


@router.post("/leagues/{league_id}/budget/broadcast", response_class=HTMLResponse)
def set_broadcast(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
    _active: ActiveLeague,
    years: int = Form(...),
):
    """Pick the length of a new broadcast deal. Only between seasons, and
    only in the season the deal is signed."""
    team_id = gm.get("team_id")
    error = None
    with league_lock(db, league_id):
        league = LeagueRepository(db).get_by_id(league_id)
        budgets = BudgetRepository(db)
        year = ContractRepository(db).current_year(league_id)
        deal = budgets.broadcast_deal(league_id, team_id, year) if year else None
        if not deal:
            error = "This league has no broadcast deals."
        elif league["state"] not in FRONT_OFFICE_STATES:
            error = "A new deal's length is picked between seasons, from the draft to Opening Day."
        elif not deal["new"]:
            error = "Your deal is locked until it runs out."
        elif years not in fn.BROADCAST_YEARS:
            error = "Pick one of the lengths offered."
        else:
            budgets.set_broadcast_years(league_id, team_id, year, years)
        db.commit()
    return _render(
        request, htmx, league_id, db, user, gm,
        broadcast_error=error, broadcast_saved=not error,
    )  # fmt: skip


@router.post("/leagues/{league_id}/budget/sponsor", response_class=HTMLResponse)
def set_sponsor(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
    _active: ActiveLeague,
    kind: str = Form(...),
):
    """Take a sponsor offer for the season. Only between seasons, like
    ticket prices."""
    team_id = gm.get("team_id")
    error = None
    with league_lock(db, league_id):
        league = LeagueRepository(db).get_by_id(league_id)
        budgets = BudgetRepository(db)
        year = ContractRepository(db).current_year(league_id)
        deal = budgets.sponsors(league_id, year, [team_id]) if year else {}
        if team_id not in deal:
            error = "This league has no sponsors."
        elif league["state"] not in FRONT_OFFICE_STATES:
            error = "Sponsor deals are signed between seasons, from the draft to Opening Day."
        elif kind not in fn.SPONSOR_KINDS:
            error = "Pick one of the offers."
        else:
            budgets.set_sponsor(league_id, team_id, year, kind)
        db.commit()
    return _render(
        request, htmx, league_id, db, user, gm,
        sponsor_error=error, sponsor_saved=not error,
    )  # fmt: skip


def _sponsor_view(deal: dict, open_: bool) -> dict:
    steady = deal["steady"]
    per_10 = fn.SPONSOR_PER_WIN_PCT * 0.1 * steady
    best = fn.sponsor_money(steady, "incentive", 0.62, True, 3)["total"]
    return {
        "kind": deal["kind"],
        "name": fn.SPONSOR_NAMES[deal["kind"]],
        "picked": deal["picked"],
        "open": open_,
        "amount_text": _money(deal["total"]),
        "steady_text": _money(steady),
        "base_text": _money(fn.sponsor_money(steady, "incentive")["base"]),
        "per_10_text": _money(per_10),
        "playoffs_text": _money(steady * fn.SPONSOR_PLAYOFFS),
        "round_text": _money(steady * fn.SPONSOR_PER_ROUND),
        "best_text": _money(best),
        "last_text": (
            f"{deal['last_win_pct']:.3f}".lstrip("0")
            if deal["last_win_pct"] is not None
            else None
        ),
        "ai_from_text": f"{fn.SPONSOR_AI_FROM:.3f}".lstrip("0"),
    }


@router.post("/leagues/{league_id}/budget/ballpark", response_class=HTMLResponse)
def build_ballpark(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
    _active: ActiveLeague,
    project: str = Form(...),
):
    """Ask the owner to build a ballpark project from their bank. Only
    between seasons; it opens on Opening Day."""
    team_id = gm.get("team_id")
    error = None
    with league_lock(db, league_id):
        league = LeagueRepository(db).get_by_id(league_id)
        budgets = BudgetRepository(db)
        year = ContractRepository(db).current_year(league_id)
        if not year or budgets.budget(league_id, team_id, year) is None:
            error = "This league has no ballpark upgrades."
        elif league["state"] not in FRONT_OFFICE_STATES:
            error = "Ballpark projects are ordered between seasons, from the draft to Opening Day."
        else:
            error = budgets.build(league_id, team_id, year, project)
        db.commit()
    return _render(
        request, htmx, league_id, db, user, gm,
        park_error=error, park_saved=not error,
    )  # fmt: skip


def _crowds_view(now: dict | None, past: list[dict], year: int, seats: int) -> dict:
    """The Crowds card: this season's home crowds so far, or last season's
    before the first home game."""
    view = {"seats": f"{seats:,}", "year": year, "so_far": True}
    if now and now["counted"]:
        c = now
        view.update(
            counted=c["counted"],
            games=c["games"],
            average=c["average"],
            full=c["full"],
            sellouts=c["sellouts"],
            best=c["best"],
            expected=round(c["in_park"] / c["counted"]),
        )
    else:
        last = next((r for r in past if r.get("crowd_games")), None)
        if last is None:
            return view
        n = last["crowd_games"]
        view.update(
            year=last["year"],
            so_far=False,
            counted=n,
            games=n,
            average=round(last["attendance"] / n),
            full=last["attendance"] / (n * last["capacity"])
            if last["capacity"]
            else None,
            sellouts=last["sellouts"] or 0,
            best=None,
            expected=None,
        )
    view["average_text"] = f"{view['average']:,}"
    view["full_pct"] = round(100 * view["full"]) if view["full"] is not None else None
    view["best_text"] = f"{view['best']:,}" if view.get("best") else None
    if view.get("expected"):
        diff = view["average"] - view["expected"]
        view["vs_text"] = (
            f"{abs(diff):,} a game {'over' if diff >= 0 else 'under'} expected"
        )
        view["vs_good"] = diff >= 0
    return view


def _ballpark_view(
    offers: list[dict], year: int, open_: bool, seats: int | None = None
) -> dict:
    rows = []
    for o in offers:
        if o["payback"] is None:
            payback = None
        else:
            seasons = max(1, round(o["payback"]))
            payback = f"Pays for itself in about {_seasons(seasons)}" + (
                " once it opens" if o["build"] else ""
            )
        if o["built"] is not None:
            status = (
                "Opens this season"
                if o["built"] == year
                else f"Building, opens {o['built']}"
                if o["built"] > year
                else f"Opened {o['built']}"
            )
            if o["rebuild"]:
                status += ", old enough to replace"
        else:
            status = None
        rows.append(
            {
                **o,
                "cost_text": _money(o["cost"]),
                "earns_text": _money(o["earns"]) if o["earns"] else None,
                "payback_text": payback,
                "short_text": _money(o["short"]) if o["short"] else None,
                "can": open_
                and (o["built"] is None or o["rebuild"])
                and not o["short"]
                and not o["waiting"]
                and not o["blocked"],
                "new": o["built"] == year,
                "status": status,
                "build_text": (
                    f"{_seasons(o['build'])} to build, opens {o['opens']}"
                    if o["build"]
                    else None
                ),
            }
        )
    return {
        "rows": rows,
        "open": open_,
        "built_count": sum(1 for o in offers if o["built"] is not None),
        "floor_caps": fn.BALLPARK_FLOOR,
        "life": fn.STADIUM_LIFE,
        "rebuild_pct": round((fn.STADIUM_REBUILD - 1) * 100),
        "seats": seats,
    }


def _broadcast_view(deal: dict, year: int, open_: bool) -> dict:
    last = deal["start_year"] + deal["years"] - 1
    return {
        "amount_text": _money(deal["amount"]),
        "years": deal["years"],
        "left": deal["left"],
        "left_text": (
            "This is its last season"
            if deal["left"] == 1
            else f"{_seasons(deal['left'])} left, through {last}"
        ),
        "signed": deal["start_year"],
        "fans": deal["fans"],
        "win_text": f"{deal['win_pct']:.3f}".lstrip("0"),
        "choosing": deal["new"],
        "open": open_ and deal["new"],
        "renews": last + 1,
        "options": [
            {
                "years": y,
                "amount_text": _money(fn.broadcast_amount(deal["base"], y)),
                "through": deal["start_year"] + y - 1,
            }
            for y in fn.BROADCAST_YEARS
        ],
    }


def _seller_names(db, books: list[dict]) -> dict[str, str]:
    ids = list(
        {
            s.player_id
            for b in books
            for s, _ in [p for p in (b.get("sellers") or []) if not p[0].hall][:3]
        }
    )
    if not ids:
        return {}
    return {
        r["id"]: f"{r['first_name'][:1]}. {r['last_name']}"
        for r in db.execute(
            "SELECT id, first_name, last_name FROM players WHERE id = ANY(%s)",
            (ids,),
        ).fetchall()
    }


def _ticket_options() -> list[dict]:
    out = []
    for level in fn.TICKET_LEVELS:
        pct = round((fn.ticket_mult(level) - 1) * 100, 1)
        fans = fn.ticket_fans(level)
        out.append(
            {
                "level": level,
                "name": fn.ticket_name(level),
                "revenue": "no change" if not pct else f"{pct:+g}%",
                "fans": "no change" if not fans else f"{fans:+d}",
                "fans_note": (
                    "no pull on where fans head each season"
                    if not fans
                    else f"{fans:+d} to where fans head each season"
                ),
            }
        )
    return out


def _league_pay(db, seasons: list[dict], my_team: str | None) -> list[dict]:
    """Every team's payroll, luxury tax and tax share by season, for the
    league table on the Budget tab."""
    ids = list({t for s in seasons for t in s["teams"]})
    names = {
        r["id"]: r
        for r in db.execute(
            "SELECT id, city, mascot FROM teams WHERE id = ANY(%s)", (ids,)
        ).fetchall()
    }
    out = []
    for s in seasons:
        cap = s["cap"]
        rows = []
        for team_id, m in s["teams"].items():
            team = names.get(team_id) or {"city": "", "mascot": team_id}
            gap = m["payroll"] - cap
            rows.append(
                {
                    "city": team["city"],
                    "mascot": team["mascot"],
                    "mine": team_id == my_team,
                    "payroll": m["payroll"],
                    "payroll_text": _money(m["payroll"]),
                    "gap": gap,
                    "gap_text": (
                        f"{_money(gap)} over"
                        if gap > 0
                        else f"{_money(-gap)} under"
                        if gap < 0
                        else "At the cap"
                    ),
                    "over": gap > 0,
                    "tax": m["tax"],
                    "tax_text": _money(m["tax"]) if m["tax"] else None,
                    "share": m["share"],
                    "share_text": _money(m["share"]) if m["share"] else None,
                }
            )
        rows.sort(key=lambda r: -r["payroll"])
        out.append(
            {
                "year": s["year"],
                "projected": s["projected"],
                "cap_text": _money(cap),
                "rows": rows,
                "pool_text": _money(sum(r["tax"] for r in rows)),
                "over_count": sum(1 for r in rows if r["over"]),
            }
        )
    return out


def _bank_seasons(past: list[dict], projected: dict | None) -> list[dict]:
    """The owner's bank season by season, newest first: what it came into
    the season with, the season's profit, what went into the ballpark and
    where it finished. This season shows its projected profit."""
    out = []
    for r in past:
        if r["bank_before"] is None:
            continue
        profit = r["profit"]
        guess = profit is None
        if guess:
            if not projected or projected["year"] != r["year"]:
                continue
            profit = projected["profit"]
        change = profit - r["bank_spent"]
        out.append(
            {
                "year": r["year"],
                "projected": guess,
                "start_text": _money(r["bank_before"]),
                "profit_text": ("+" if profit >= 0 else "") + _money(profit),
                "loss": profit < 0,
                "spent_text": _money(-r["bank_spent"]) if r["bank_spent"] else None,
                "end_text": _money(r["bank_before"] + change),
                "change_text": ("+" if change >= 0 else "") + _money(change),
                "down": change < 0,
            }
        )
    return out


def _render(
    request, htmx, league_id, db, user, gm, error=None, saved=False,
    ticket_error=None, ticket_saved=False,
    broadcast_error=None, broadcast_saved=False,
    sponsor_error=None, sponsor_saved=False,
    park_error=None, park_saved=False,
):  # fmt: skip
    ctx = _shell_ctx(request, db, gm, league_id, "budget", user)
    ctx["park_error"] = park_error
    ctx["park_saved"] = park_saved
    ctx["sponsor_error"] = sponsor_error
    ctx["sponsor_saved"] = sponsor_saved
    ctx["broadcast_error"] = broadcast_error
    ctx["broadcast_saved"] = broadcast_saved
    ctx["fo_error"] = error
    ctx["fo_saved"] = saved
    ctx["ticket_error"] = ticket_error
    ctx["ticket_saved"] = ticket_saved
    team_id = gm.get("team_id")
    budgets = BudgetRepository(db)
    year = ContractRepository(db).current_year(league_id)
    standing = (
        budgets.standing(league_id, team_id, year)
        if team_id and year is not None
        else None
    )
    ctx["year"] = year
    ctx["money"] = standing
    past = budgets.history(league_id, team_id) if standing else []
    if standing:
        from src.player.contracts import minors_salary

        ctx["farm_pay_text"] = _money(
            minors_salary(budgets.salary_scale(league_id, year))
        )
    bank = budgets.banks(league_id).get(team_id) if standing else None
    if bank:
        ctx["bank"] = {
            "balance_text": _money(bank["balance"]),
            "change_text": _money(bank["change"]),
            "start_text": _money(bank["start"]),
            "since": bank["since"],
            "up": bank["change"] >= 0,
            "empty": bank["balance"] <= 0,
            "spent_text": _money(bank["spent"]) if bank["spent"] else None,
            # What the owner will put into the ballpark: all but a cap.
            "free_text": _money(
                max(
                    0,
                    bank["balance"]
                    - bank["owed"]
                    - round(standing["cap"] * fn.BALLPARK_FLOOR),
                )
            ),
            "owed_text": _money(bank["owed"]) if bank["owed"] else None,
            "floor_text": _money(round(standing["cap"] * fn.BALLPARK_FLOOR)),
        }
    if standing and ctx.get("league_state") in FRONT_OFFICE_STATES:
        # The GM has had their chance to set the budget before it locks:
        # the preseason's next move stops asking (next_move.pick).
        budgets.mark_budget_seen(league_id, team_id, year)
    if standing:
        cap = standing["cap"]
        levels = budgets.levels(league_id, team_id, year)
        ctx["front_office"] = [
            {
                "key": key,
                "label": label,
                "what": what,
                "level": levels[key],
                "options": [
                    {
                        "level": i,
                        "name": name,
                        "cost_text": format_salary(bg.level_cost(cap, i)),
                    }
                    for i, name in enumerate(bg.LEVELS)
                ],
            }
            for key, label, what in bg.DEPARTMENTS
        ]
        ctx["fo_open"] = ctx.get("league_state") in FRONT_OFFICE_STATES
        level = budgets.ticket_price(league_id, team_id, year)
        ctx["tickets"] = {
            "level": level,
            "options": _ticket_options(),
            "fans_now": budgets.fans_now(league_id, team_id, year),
        }
        deal = budgets.broadcast_deal(league_id, team_id, year)
        ctx["broadcast"] = _broadcast_view(deal, year, ctx["fo_open"]) if deal else None
        sponsor = budgets.sponsors(league_id, year, [team_id]).get(team_id)
        ctx["sponsor"] = _sponsor_view(sponsor, ctx["fo_open"]) if sponsor else None
        offers = budgets.ballpark_offers(league_id, team_id, year)
        seats = fn.capacity(budgets.ballparks(league_id, year).get(team_id, ()))
        ctx["ballpark"] = (
            _ballpark_view(offers, year, ctx["fo_open"], seats)
            if offers and bank
            else None
        )
        ctx["crowds"] = _crowds_view(
            budgets.crowds(league_id, year, [team_id]).get(team_id),
            past,
            year,
            seats,
        )
    ctx["rules"] = {
        "tax_pct": round(bg.LUXURY_TAX_RATE * 100),
        "pull_pct": round(bg.BANK_PULL * 100),
        "swing_pct": round(bg.BANK_SWING * 100),
        "margin_pct": round(bg.HARD_MARGIN * 100),
        "gate_pct": round(fn.GATE_SHARE * 100),
    }
    books = budgets.books(league_id, team_id, year) if standing else []
    names = _seller_names(db, books)
    ctx["books"] = [_books_view(b, names) for b in books]
    ctx["history"] = _past_seasons(past, books)
    ctx["history_other"] = any(r["other"] for r in ctx["history"])
    ctx["history_park"] = any(r["park"] for r in ctx["history"])
    if bank and books and books[0]["projected"]:
        # This season's projected profit, and where it leaves the bank.
        profit = books[0]["profit"]
        ctx["bank"]["profit_text"] = _money(profit)
        ctx["bank"]["profit_loss"] = profit < 0
        ctx["bank"]["after_text"] = _money(bank["balance"] + profit)
        ctx["bank"]["year"] = books[0]["year"]
    if bank:
        ctx["bank"]["seasons"] = _bank_seasons(
            past, books[0] if books and books[0]["projected"] else None
        )
    ctx["league_pay"] = (
        _league_pay(db, budgets.league_payrolls(league_id, year), team_id)
        if standing
        else []
    )
    db.commit()  # banks open on first look
    return tab_response(request, htmx, "dashboard/partials/budget.html", ctx)
