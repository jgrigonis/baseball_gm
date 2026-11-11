# src/api/services/trade_shop.py
#
# Shopping a player: a GM asks every AI team at once what it would give for
# one of their players, instead of building offers team by team.
#
# Each AI team puts together its best package of one or two of its own
# players that it would really take the deal for (src/league/trades/
# ai_proposer.py, shop_offer), judged exactly as it judges an offer: its team
# state, its GM's persona and margin for this team today, its owner's
# budget. The offers come back sorted by how much they help the GM's team.
# Teams with no deal they'd take are listed as having no interest.
#
# Everything is fixed for the league day (the margins are seeded by the
# date), so shopping again the same day gives the same list. Shopping isn't
# an offer, so it doesn't count toward the calls a team will take in a day.
# Taking an offer (take) works it out again and makes it as a normal
# trade, which the AI answers at once, as it would any offer.
#
# In a league with other people, they hear (news bar) that the player is on
# the block, once a league day, so they can make an offer too.
#
# Dumping salary (dump, dump_take) is the same call made for the money: each
# AI team says what it would take the player for, sending back one cheap
# throw-in, with a sweetener from the GM when he alone isn't worth it to
# them (ai_proposer.dump_offer_or_why). Cheapest for the GM first.
#
# Absorbing salary (absorb, absorb_take) is a dump the other way round: the
# GM sends the player and takes on one or two of an AI team's big contracts
# it would rather be rid of (ai_proposer.absorb_offer_or_why). The AI saves
# money, the GM gets players. Most help to the GM first.
#
# The Trades tab keeps the last shop or dump in the browser, so leaving the
# tab and coming back shows it again. It's kept with stamp(): once the day,
# the league's state, any roster or any contract changes, the stamp does too
# and the page drops the old list.

from __future__ import annotations

from src.api.services import owners, personas, team_states, trades
from src.db.locks import LeagueBusy, league_lock
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.contract_repo import ContractRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.notification_repo import NotificationRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.trade_repo import TradeRepository
from src.league import budget as bg
from src.league import trade_deadline
from src.league.personas import Leanings
from src.league.trades import ai_evaluator
from src.league.trades.ai_proposer import (
    AbsorbOffer,
    DumpOffer,
    ShopOffer,
    Side,
    absorb_offer_or_why,
    dump_offer_or_why,
    shop_offer_or_why,
)


class _Ctx:
    """What a shop needs: the league, the day, and the GM's side."""

    def __init__(self, conn, league_id: str, gm: dict, player_id: str):
        self.conn = conn
        self.league_id = league_id
        self.league = dict(LeagueRepository(conn).get_by_id(league_id))
        self.season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
        trades._check_window(conn, self.league, self.season_id)
        self.team_id = gm.get("team_id")
        if not self.team_id:
            raise trades.TradeError("You don't run a team in this league.")
        if player_id not in PlayerRepository(conn).get_player_ids_from_team_players(
            self.team_id
        ):
            raise trades.TradeError("He isn't on your team.")
        if PlayerStatusRepository(conn).get_status(player_id) not in trades.TRADEABLE:
            raise trades.TradeError("He can't be traded.")
        self.player_id = player_id
        self.today = trades._league_date(conn, self.season_id)
        self.days_left = trades._season_days_left(
            conn, league_id, self.season_id, self.today
        )
        self.injuries = InjuryRepository(conn, league_id)
        self.leanings = personas.leanings(conn, league_id)
        self.humans = set(GMRepository(conn).get_human_team_ids(league_id))
        self.trade_repo = TradeRepository(conn)
        roster = self._roster(self.team_id)
        self.target = next(a for a in roster if a.id == player_id)
        self.seller = Side(
            team_id=self.team_id,
            state=self._state(self.team_id),
            roster=roster,
            tradeable=set(),
            margin=0.0,
            stats_weight=self.leanings.get(self.team_id, Leanings()).stats_weight,
        )
        self._rooms = None
        self._terms = None
        self._fits = None

    def seller_tradeable(self) -> None:
        """Let the GM's other players be offered as sweeteners (a dump)."""
        statuses = _statuses(self.conn, self.team_id)
        self.seller.tradeable = {
            a.id for a in self.seller.roster if statuses.get(a.id) in trades.TRADEABLE
        }

    def _roster(self, team_id: str):
        hurt = self.injuries.get_team_injuries(team_id, self.today)
        return trades._assets(self.conn, team_id, hurt, self.season_id)

    def _state(self, team_id: str) -> str:
        return team_states.state_of(
            self.conn, self.league_id, self.season_id, team_id, self.today
        )

    def ai_teams(self) -> list[dict]:
        return [
            t
            for t in TeamRepository(self.conn).get_teams_in_league_season(
                self.league_id, self.season_id
            )
            if t["id"] != self.team_id and t["id"] not in self.humans
        ]

    def offer_from(self, team_id: str) -> ShopOffer | None:
        """This AI team's best offer, as its answer to the offer would be."""
        offer = self.offer_or_why(team_id)
        return offer if isinstance(offer, ShopOffer) and not offer.short else None

    def offer_or_why(self, team_id: str) -> ShopOffer | str:
        """This AI team's best offer, or why it has none (TRADED_HIM, or
        ai_proposer.shop_offer_or_why)."""
        side = self._ai_side(team_id)
        if isinstance(side, str):
            return side
        ai, blocked = side
        return shop_offer_or_why(ai, self.seller, self.target, self.days_left, blocked)

    def dump_or_why(self, team_id: str) -> DumpOffer | str:
        """What this AI team would take the player's salary for, or why
        not (TRADED_HIM, or ai_proposer.dump_offer_or_why)."""
        side = self._ai_side(team_id)
        if isinstance(side, str):
            return side
        ai, blocked = side
        # A sweetener can't go back to a team that traded him away either.
        mine = [a.id for a in self.seller.roster if a.id in self.seller.tradeable]
        back = self.trade_repo.former_teams(self.season_id, mine)
        seller = self.seller
        gone = {pid for pid, teams in back.items() if team_id in teams}
        if gone:
            seller = Side(
                team_id=self.seller.team_id,
                state=self.seller.state,
                roster=self.seller.roster,
                tradeable=self.seller.tradeable - gone,
                margin=0.0,
                stats_weight=self.seller.stats_weight,
            )
        return dump_offer_or_why(ai, seller, self.target, self.days_left, blocked)

    def absorb_or_why(self, team_id: str) -> AbsorbOffer | str:
        """The big contracts this AI team would send for the player, or why
        not (TRADED_HIM, or ai_proposer.absorb_offer_or_why)."""
        side = self._ai_side(team_id)
        if isinstance(side, str):
            return side
        ai, blocked = side
        return absorb_offer_or_why(
            ai, self.seller, self.target, self.days_left, blocked, self.owner_fits()
        )

    def owner_fits(self):
        """fits(added) for the GM's owner's hard limit (trades.owner_refusal,
        worked out once), or None without budgets."""
        if self._fits is None:
            budgets = BudgetRepository(self.conn)
            year = trades._season_year(self.conn, self.season_id)
            standing = (
                budgets.standing(self.league_id, self.team_id, year)
                if year and budgets.enabled(self.league_id)
                else None
            )
            if standing is None:
                self._fits = False
            else:

                def fits(added: int) -> bool:
                    cost = bg.added_cost(standing["payroll"], standing["cap"], added)
                    return (
                        bg.refusal(standing["spend"], standing["limit"], cost) is None
                    )

                self._fits = fits
        return self._fits or None

    def _ai_side(self, team_id: str) -> tuple[Side, set[str]] | str:
        """The AI team as the search sees it, and its players who can't go
        to the GM; or TRADED_HIM."""
        # A player can't go back to a team that traded him away this season.
        former = self.trade_repo.former_teams(self.season_id, [self.player_id])
        if team_id in former.get(self.player_id, ()):
            return TRADED_HIM
        roster = self._roster(team_id)
        statuses = _statuses(self.conn, team_id)
        tradeable = {a.id for a in roster if statuses.get(a.id) in trades.TRADEABLE}
        back = self.trade_repo.former_teams(self.season_id, list(tradeable))
        blocked = {pid for pid, teams in back.items() if self.team_id in teams}
        if self._rooms is None:
            self._rooms = owners.pay_rooms(self.conn, self.league_id, self.season_id)
            self._terms = owners.money_terms(self.conn, self.league_id, self.season_id)
        lean = self.leanings.get(team_id, Leanings())
        state = self._state(team_id)
        ai = Side(
            team_id=team_id,
            state=state,
            roster=roster,
            tradeable=tradeable,
            # The same margin it would answer this GM's offer with today
            # (trades.ai_answer).
            margin=ai_evaluator.margin(
                team_id, self.team_id, self.today, lean.margin_factor
            ),
            stats_weight=lean.stats_weight,
            horizon=lean.horizon,
            pay_room=self._rooms.get(team_id),
            money=owners.money_rate(self._terms, self._rooms.get(team_id), state),
        )
        return ai, blocked


# A team that traded him away this season can't take him back.
TRADED_HIM = "traded"


def _statuses(conn, team_id: str) -> dict[str, str]:
    rows = conn.execute(
        """SELECT tp.player_id, s.status FROM team_players tp
           JOIN player_status s ON s.player_id = tp.player_id
           WHERE tp.team_id = %s""",
        (team_id,),
    ).fetchall()
    return {r["player_id"]: r["status"] for r in rows}


def stamp(conn, league_id: str) -> str:
    """What a shop's answers hang on, as one string: the league day and
    state, and a fingerprint of every roster spot, roster status and
    contract in the league. A kept shop list is shown again only while this
    is unchanged."""
    league = LeagueRepository(conn).get_by_id(league_id)
    season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
    if not league or not season_id:
        return ""
    row = conn.execute(
        """
        SELECT md5(COALESCE(string_agg(
                   tp.team_id || ':' || tp.player_id || ':' || COALESCE(ps.status, ''),
                   ',' ORDER BY tp.team_id, tp.player_id), '')) AS rosters,
               (SELECT COALESCE(MAX(id), 0) FROM player_contracts
                 WHERE league_id = %s) AS contracts
        FROM league_season_teams lst
        JOIN team_players tp ON tp.team_id = lst.team_id
        LEFT JOIN player_status ps ON ps.player_id = tp.player_id
        WHERE lst.league_id = %s AND lst.season_id = %s
        """,
        (league_id, league_id, season_id),
    ).fetchone()
    today = trades._league_date(conn, season_id) or ""
    return f"{league['state']}|{today}|{row['rosters']}|{row['contracts']}"


def shop(conn, league_id: str, gm: dict, player_id: str) -> dict:
    """Every AI team's best offer for the GM's player:
    {"player", "offers": [{team_id, team_name, give: [ids], score}], best
    for the GM first, "close": the same for teams that want him but have no
    deal they'd take (the package each came closest to taking, best for the
    GM first, the near ones (it would come out ahead, just not by its
    margin) before the rest), "no_interest": [team names], "why": {reason: [team names]}}
    (reasons: ai_proposer.NO_HELP/NO_VALUE/NO_ROOM/NO_MATCH, TRADED_HIM)."""
    ctx = _Ctx(conn, league_id, gm, player_id)
    offers, close, none, why = [], [], [], {}
    for t in ctx.ai_teams():
        name = f"{t['city']} {t['mascot']}"
        offer = ctx.offer_or_why(t["id"])
        if not isinstance(offer, ShopOffer):
            none.append(name)
            why.setdefault(offer, []).append(name)
            continue
        (close if offer.short else offers).append(
            {
                "team_id": t["id"],
                "team_name": name,
                "give": [a.id for a in offer.give],
                "score": round(offer.score, 1),
                **({"near": offer.near} if offer.short else {}),
            }
        )
    offers.sort(key=lambda o: o["score"], reverse=True)
    close.sort(key=lambda o: (o["near"], o["score"]), reverse=True)
    _tell_other_gms(conn, ctx, gm)
    conn.commit()
    return {
        "player": ctx.target.name,
        "offers": offers,
        "close": close,
        "no_interest": sorted(none),
        "why": {k: sorted(v) for k, v in why.items()},
        "offseason": ctx.league["state"] in trade_deadline.OFFSEASON_STATES,
    }


def take(conn, league_id: str, gm: dict, player_id: str, team_id: str) -> dict:
    """Make the AI team's shop offer for the GM's player as a trade, worked
    out again now. Answers like trades.propose for an AI team."""
    try:
        with league_lock(conn, league_id):
            ctx = _Ctx(conn, league_id, gm, player_id)
            if team_id not in {t["id"] for t in ctx.ai_teams()}:
                raise trades.TradeError("That team isn't taking offers here.")
            offer = ctx.offer_from(team_id)
            if offer is None:
                raise trades.TradeError(
                    f"The {TeamRepository(conn).get_name(team_id)} aren't "
                    "interested any more."
                )
            return trades._propose(
                conn,
                league_id,
                gm,
                team_id,
                [player_id],
                [a.id for a in offer.give],
                None,
                call_limit=False,
            )
    except LeagueBusy:
        raise trades.TradeError("Games are being played. Try again in a moment.")


def dump(conn, league_id: str, gm: dict, player_id: str) -> dict:
    """What every AI team would take the GM's player's salary for:
    {"player", "salary", "guaranteed", "offers": [{team_id, team_name,
    give: [ids], add: [ids], saved, unguaranteed}], those that take him
    alone first (most saved first), then by how little the sweetener costs
    the GM, "why": {reason: [team names]}} (reasons: ai_proposer.NO_ROOM/
    NO_SAVING/NO_MATCH, TRADED_HIM). A player whose deal isn't guaranteed
    has no salary to dump: no offers, "guaranteed" False."""
    ctx = _Ctx(conn, league_id, gm, player_id)
    if not _guaranteed(conn, ctx):
        # Nothing to dump: sending him down or releasing him clears it free.
        return {
            "player": ctx.target.name,
            "salary": ctx.target.salary,
            "guaranteed": False,
            "offers": [],
            "why": {},
        }
    ctx.seller_tradeable()
    offers, why = [], {}
    for t in ctx.ai_teams():
        name = f"{t['city']} {t['mascot']}"
        offer = ctx.dump_or_why(t["id"])
        if not isinstance(offer, DumpOffer):
            why.setdefault(offer, []).append(name)
            continue
        offers.append(
            {
                "team_id": t["id"],
                "team_name": name,
                "give": [a.id for a in offer.give],
                "add": [a.id for a in offer.add],
                "saved": offer.saved,
                "_cost": offer.cost,
            }
        )
    _payroll_effects(conn, ctx, offers)
    offers.sort(key=lambda o: (bool(o["add"]), o["_cost"], -o["saved"]))
    for o in offers:
        del o["_cost"]
    _tell_other_gms(conn, ctx, gm)
    conn.commit()
    return {
        "player": ctx.target.name,
        "salary": ctx.target.salary,
        "guaranteed": True,
        "offers": offers,
        "why": {k: sorted(v) for k, v in why.items()},
    }


def _guaranteed(conn, ctx: _Ctx) -> bool:
    """Whether the player's deal this season is guaranteed (he's played a
    game on the 40-man under it). Only then is there salary to dump."""
    year = trades._season_year(conn, ctx.season_id)
    deal = ContractRepository(conn).active(ctx.player_id, year) if year else None
    return bool(deal and deal["guaranteed"])


def _payroll_effects(
    conn, ctx: _Ctx, offers: list[dict], out_counts: str = "guaranteed"
) -> None:
    """Set each dump offer's "saved": what it really does to the GM's
    payroll this season: the guaranteed deals going out (the dumped player
    and any sweetener; one not guaranteed comes off free anyway) less what
    the throw-in adds to his team's now (a guaranteed deal or one on the
    40-man). "unguaranteed": the deals of throw-ins not on a payroll now
    (farm players), which count only once they're put on the 40-man.
    out_counts "on_payroll": count the GM's player as he's on the payroll
    now (an absorb, where he goes either way)."""
    year = trades._season_year(conn, ctx.season_id)
    ids = {ctx.player_id}
    for o in offers:
        ids.update(o["give"], o["add"])
    deals = ContractRepository(conn).active_for(ids, year) if year else {}

    def pay(pid, counts) -> int:
        d = deals.get(pid)
        return d["salary"] if d and d[counts] else 0

    for o in offers:
        out = sum(pay(pid, out_counts) for pid in [ctx.player_id] + o["add"])
        held = sum(pay(pid, "on_payroll") for pid in o["give"])
        o["saved"] = out - held
        o["unguaranteed"] = sum(
            deals[pid]["salary"]
            for pid in o["give"]
            if pid in deals and not deals[pid]["on_payroll"]
        )
        o["through"] = {
            pid: deals[pid]["start_year"] + deals[pid]["years"] - 1
            for pid in o["give"]
            if pid in deals
        }


def dump_take(conn, league_id: str, gm: dict, player_id: str, team_id: str) -> dict:
    """Make the AI team's dump offer as a trade, worked out again now.
    Answers like trades.propose for an AI team."""
    try:
        with league_lock(conn, league_id):
            ctx = _Ctx(conn, league_id, gm, player_id)
            if not _guaranteed(conn, ctx):
                raise trades.TradeError(
                    "His deal isn't guaranteed: send him down or release him instead."
                )
            ctx.seller_tradeable()
            if team_id not in {t["id"] for t in ctx.ai_teams()}:
                raise trades.TradeError("That team isn't taking offers here.")
            offer = ctx.dump_or_why(team_id)
            if not isinstance(offer, DumpOffer):
                raise trades.TradeError(
                    f"The {TeamRepository(conn).get_name(team_id)} won't take "
                    "him any more."
                )
            return trades._propose(
                conn,
                league_id,
                gm,
                team_id,
                [player_id] + [a.id for a in offer.add],
                [a.id for a in offer.give],
                None,
                call_limit=False,
            )
    except LeagueBusy:
        raise trades.TradeError("Games are being played. Try again in a moment.")


def absorb(conn, league_id: str, gm: dict, player_id: str) -> dict:
    """Which AI teams would send big contracts they'd rather be rid of for
    the GM's player: {"player", "salary", "offers": [{team_id, team_name,
    give: [ids], saved (negative: what it adds to the GM's payroll this
    season), unguaranteed, score}], most help to the GM first, "why":
    {reason: [team names]}} (reasons: ai_proposer.NO_BIG/NO_MATCH/NO_USE/
    NO_LIMIT, TRADED_HIM)."""
    ctx = _Ctx(conn, league_id, gm, player_id)
    offers, why = [], {}
    for t in ctx.ai_teams():
        name = f"{t['city']} {t['mascot']}"
        offer = ctx.absorb_or_why(t["id"])
        if not isinstance(offer, AbsorbOffer):
            why.setdefault(offer, []).append(name)
            continue
        offers.append(
            {
                "team_id": t["id"],
                "team_name": name,
                "give": [a.id for a in offer.give],
                "add": [],
                "score": round(offer.score, 1),
            }
        )
    _payroll_effects(conn, ctx, offers, out_counts="on_payroll")
    offers.sort(key=lambda o: o["score"], reverse=True)
    _tell_other_gms(conn, ctx, gm)
    conn.commit()
    return {
        "player": ctx.target.name,
        "salary": ctx.target.salary,
        "offers": offers,
        "why": {k: sorted(v) for k, v in why.items()},
    }


def absorb_take(conn, league_id: str, gm: dict, player_id: str, team_id: str) -> dict:
    """Make the AI team's absorb offer as a trade, worked out again now.
    Answers like trades.propose for an AI team."""
    try:
        with league_lock(conn, league_id):
            ctx = _Ctx(conn, league_id, gm, player_id)
            if team_id not in {t["id"] for t in ctx.ai_teams()}:
                raise trades.TradeError("That team isn't taking offers here.")
            offer = ctx.absorb_or_why(team_id)
            if not isinstance(offer, AbsorbOffer):
                raise trades.TradeError(
                    f"The {TeamRepository(conn).get_name(team_id)} won't make "
                    "that deal any more."
                )
            return trades._propose(
                conn,
                league_id,
                gm,
                team_id,
                [player_id],
                [a.id for a in offer.give],
                None,
                call_limit=False,
            )
    except LeagueBusy:
        raise trades.TradeError("Games are being played. Try again in a moment.")


def _tell_other_gms(conn, ctx: _Ctx, gm: dict) -> None:
    """In a league with other people, tell them he's on the block, once a
    league day."""
    others = [
        g
        for g, team in GMRepository(conn).get_human_gm_teams(ctx.league_id).items()
        if team != ctx.team_id
    ]
    if not others:
        return
    seen = conn.execute(
        """SELECT 1 FROM gm_notifications
           WHERE kind = 'trade' AND payload->>'event' = 'block'
             AND payload->>'player_id' = %s AND payload->>'on' = %s LIMIT 1""",
        (ctx.player_id, ctx.today),
    ).fetchone()
    if seen:
        return
    team = TeamRepository(conn).get_name(ctx.team_id)
    text = f"The {team} are shopping {ctx.target.name}. Make them an offer."
    repo = NotificationRepository(conn)
    for g in others:
        repo.add(
            g,
            "trade",
            {
                "event": "block",
                "offer_id": None,
                "player_id": ctx.player_id,
                "on": ctx.today,
                "text": text,
                "popup": False,
            },
        )
