# src/api/services/trades.py
#
# Proposing and carrying out trades (see plans/trades.md).
#
# An offer to an AI team gets its answer at once (see
# src/league/trades/ai_evaluator.py). An offer to a team another person runs
# waits for that GM, who can accept, reject or counter it (a counter is a new
# offer the other way, and the first one becomes 'countered'); the GM who
# made it can withdraw it. It expires before the period after the one it was
# made in runs, so the other GM always gets one whole Decision Window, and at
# the trade deadline.
#
# League vote: in a league with trade_vote on, a trade two GMs agree on goes
# to the league's other GMs (the ones not away) and waits as pending_vote. It
# passes with yes votes from more than half of them, and a GM who hasn't
# voted when the vote closes (before the next period runs, or at the
# deadline) counts as a no. With nobody to vote, it goes straight through.
#
# Rules checked on every offer, and again when a GM accepts one:
#   - the league trades (Blitz; not Speed Blitz, not Long Form yet) and the
#     window is open: from the end of the playoffs, through the offseason and
#     the draft, until deadline day's games (src/league/trade_deadline.py)
#   - 1 to MAX_PER_SIDE players or draft picks a side, each owned by the side
#     giving it up. Picks only with the league's pick_trades on, and only the
#     next draft's first rounds (src/league/trades/draft_picks.py)
#   - no player goes back to a team that traded him away this season
#   - an AI team that turned down MAX_REJECTIONS_A_DAY offers from a team
#     today won't hear another until tomorrow
#   - a GM has at most MAX_OPEN_OFFERS offers out to other GMs, and one to
#     any one team
#
# A trade runs under the league lock, so it can't overlap a sim, and counts
# from the next game. Running the offseason (a new season) closes every open
# offer, and the draft calls off the ones with its picks in them. Traded players arrive in the organization (minors),
# never on the 40-man, so a trade can't push a roster over 40. A team left
# under 25 has the best of its organization called up before its next game
# (src/team/roster_limits.py), unless the GM does it first. Every other open
# offer naming a traded player is called off.
#
# Each GM hears about their trades as gm_notifications kind 'trade', with an
# `event`: offer, counter and vote pop up (the shell's trade popup); the rest
# go in the news bar.

from __future__ import annotations

from datetime import date

from src.db.locks import LeagueBusy, league_lock
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.notification_repo import NotificationRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.ready_check_repo import ReadyCheckRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.standings_repo import StandingsRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.trade_repo import TradeRepository
from src.league import trade_deadline
from src.league.rotation_seeder import seed_ai_rotations
from src.league.trades import ai_evaluator, draft_picks
from src.league.trades.ai_evaluator import Asset
from src.team.roster_assigner import RosterAssigner
from src.team.roster_limits import playing_count

MAX_PER_SIDE = 5
MAX_REJECTIONS_A_DAY = 3
MAX_OPEN_OFFERS = 5

# Trade news that pops up rather than going in the news bar: something the
# GM has to answer.
POPUP_EVENTS = ("offer", "counter", "vote")

# Statuses a player can be traded from.
TRADEABLE = ("26man", "40man", "minors")

# How much of a season the AI looks ahead to in the offseason, when there's
# no season left to play: about a whole one.
OFFSEASON_DAYS_LEFT = 180

# Stances, once STANCE_MIN_GAMES are played: a team in the playoff picture
# (top PLAYOFF_SPOTS, or within CONTENDER_GB games of the last spot) buys for
# now, and one more than SELLER_GB back sells. Everyone else is neutral.
PLAYOFF_SPOTS = 8
CONTENDER_GB = 5
SELLER_GB = 10
STANCE_MIN_GAMES = 20


class TradeError(ValueError):
    """An offer that breaks a rule. The message is shown to the GM."""


def propose(
    conn,
    league_id: str,
    gm: dict,
    to_team_id: str,
    give_ids: list[str],
    get_ids: list[str],
    counter_of: str | None = None,
) -> dict:
    """Offer give_ids from the GM's team for get_ids from to_team_id, or, with
    counter_of, answer that offer to the GM with this one instead.

    An AI team answers at once, and an accepted trade is carried out before
    returning: {"accepted", "reason", "offer_id", "arrived", "playing_count"}.
    An offer to another GM waits for them: {"pending": True, "offer_id"}."""
    try:
        with league_lock(conn, league_id):
            return _propose(
                conn, league_id, gm, to_team_id, give_ids, get_ids, counter_of
            )
    except LeagueBusy:
        raise TradeError("Games are being played. Try again in a moment.")


def _propose(conn, league_id, gm, to_team_id, give_ids, get_ids, counter_of):
    league = dict(LeagueRepository(conn).get_by_id(league_id))
    season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
    _check_window(conn, league, season_id)

    my_team_id = gm["team_id"]
    team_repo = TeamRepository(conn)
    if to_team_id == my_team_id:
        raise TradeError("Pick another team to trade with.")
    if not team_repo.is_in_league(to_team_id, league_id, season_id):
        raise TradeError("That team isn't in this league.")

    trade_repo = TradeRepository(conn)
    parent = None
    if counter_of:
        parent = trade_repo.get(counter_of)
        if (
            not parent
            or parent["league_id"] != league_id
            or parent["status"] != "pending"
            or parent["to_team_id"] != my_team_id
            or parent["from_team_id"] != to_team_id
        ):
            raise TradeError("That offer can't be countered any more.")

    give_ids, get_ids = _dedupe(give_ids), _dedupe(get_ids)
    names = _check_assets(
        conn, league, season_id, my_team_id, to_team_id, give_ids, get_ids
    )
    today = _league_date(conn, season_id)
    items = [(pid, my_team_id) for pid in give_ids] + [
        (pid, to_team_id) for pid in get_ids
    ]

    if GMRepository(conn).get_human_gm_for_team(league_id, to_team_id):
        return _offer_to_gm(
            conn, league_id, season_id, gm, to_team_id, items, today, parent
        )

    if (
        trade_repo.rejections_today(league_id, my_team_id, to_team_id, today)
        >= MAX_REJECTIONS_A_DAY
    ):
        raise TradeError(
            f"The {team_repo.get_name(to_team_id)} aren't taking any more calls today."
        )
    if parent:
        _decide(conn, parent["id"], "countered", None)

    offer_id = trade_repo.create_offer(
        league_id,
        season_id,
        my_team_id,
        to_team_id,
        gm.get("id"),
        today,
        items,
        parent_id=parent["id"] if parent else None,
    )
    verdict = ai_answer(
        conn, league_id, season_id, to_team_id, my_team_id, get_ids, give_ids, today
    )
    if not verdict.accept:
        _decide(conn, offer_id, "rejected", verdict.reason)
        conn.commit()
        return {
            "accepted": False,
            "reason": verdict.reason,
            "offer_id": offer_id,
        }

    _decide(conn, offer_id, "accepted", verdict.reason)
    execute(
        conn,
        league_id,
        season_id,
        {my_team_id: give_ids, to_team_id: get_ids},
        _next_game_date(conn, season_id),
    )
    conn.commit()
    return {
        "accepted": True,
        "reason": verdict.reason,
        "offer_id": offer_id,
        "arrived": [names[pid] for pid in get_ids],
        "playing_count": playing_count(conn, my_team_id),
    }


def _check_window(conn, league: dict, season_id) -> None:
    window = trade_deadline.window(conn, league, season_id)
    if not window["enabled"]:
        raise TradeError("This league doesn't have trades.")
    if not window["open"]:
        raise TradeError("The trade window is closed.")


def _check_assets(
    conn, league: dict, season_id, from_team, to_team, give_ids, get_ids
) -> dict:
    """Raise TradeError unless from_team can trade give_ids for to_team's
    get_ids (players and draft picks). Returns {id: name}."""
    if not give_ids or not get_ids:
        raise TradeError("Each side has to give up at least one player or pick.")
    if len(give_ids) > MAX_PER_SIDE or len(get_ids) > MAX_PER_SIDE:
        raise TradeError(f"At most {MAX_PER_SIDE} players or picks a side.")

    names = _check_picks(
        conn,
        league,
        season_id,
        [(from_team, i) for i in give_ids if draft_picks.is_pick(i)]
        + [(to_team, i) for i in get_ids if draft_picks.is_pick(i)],
    )
    give_ids = [i for i in give_ids if not draft_picks.is_pick(i)]
    get_ids = [i for i in get_ids if not draft_picks.is_pick(i)]

    player_repo = PlayerRepository(conn)
    status_repo = PlayerStatusRepository(conn)
    for side, ids in ((from_team, give_ids), (to_team, get_ids)):
        owned = player_repo.get_player_ids_from_team_players(side)
        for pid in ids:
            if pid not in owned:
                raise TradeError("A player in the offer isn't on that team any more.")
            if status_repo.get_status(pid) not in TRADEABLE:
                raise TradeError("A player in the offer can't be traded.")
            p = player_repo.look_up(pid)
            names[pid] = p.name if p else pid

    team_repo = TeamRepository(conn)
    former = TradeRepository(conn).former_teams(season_id, give_ids + get_ids)
    for pid in give_ids:
        if to_team in former.get(pid, ()):
            raise TradeError(
                f"{names[pid]} can't go back to the {team_repo.get_name(to_team)} this season."
            )
    for pid in get_ids:
        if from_team in former.get(pid, ()):
            raise TradeError(
                f"{names[pid]} can't go back to the {team_repo.get_name(from_team)} this season."
            )
    return names


def _check_picks(conn, league: dict, season_id, picks) -> dict:
    """Raise TradeError unless each (team, pick id) is a pick that team owns
    and can trade. Returns {pick id: label}."""
    if not picks:
        return {}
    if not draft_picks.enabled(league):
        raise TradeError("This league doesn't trade draft picks.")
    year = _pick_year(conn, league, season_id)
    team_repo = TeamRepository(conn)
    names = {}
    for team_id, pick_id in picks:
        pick = draft_picks.parse(pick_id)
        if not pick or pick.draft_year != year:
            raise TradeError(f"Only picks in the {year} draft can be traded.")
        if pick.round > draft_picks.TRADEABLE_ROUNDS:
            raise TradeError(
                f"Only the first {draft_picks.TRADEABLE_ROUNDS} rounds' picks trade."
            )
        if draft_picks.owner(conn, league["id"], pick) != team_id:
            raise TradeError("A pick in the offer isn't that team's any more.")
        names[pick_id] = draft_picks.label(
            pick, team_repo.get_name(pick.original_team_id)
        )
    return names


def _pick_year(conn, league: dict, season_id) -> int | None:
    """The draft whose picks trade now. Its rights are written the first time
    they're needed."""
    season = SeasonRepository(conn).get_season(season_id) if season_id else None
    year = draft_picks.draft_year(conn, league, season["year"] if season else None)
    if year is not None:
        teams = TeamRepository(conn).get_teams_in_league_season(league["id"], season_id)
        draft_picks.ensure_rights(conn, league["id"], year, [t["id"] for t in teams])
    return year


def pick_cards(conn, league: dict, season_id, team_id: str) -> list[dict]:
    """A team's tradeable draft picks for the offer builder, shaped like its
    player cards (roster_status 'pick'). Empty unless the league trades
    picks."""
    if not draft_picks.enabled(league) or not season_id:
        return []
    year = _pick_year(conn, league, season_id)
    if year is None:
        return []
    slots, teams = draft_picks.projected_slots(conn, league["id"], season_id, year)
    team_repo = TeamRepository(conn)
    cards = []
    for pick in draft_picks.owned(conn, league["id"], year, team_id):
        slot = draft_picks.slot_in_round(
            pick, slots.get(pick.original_team_id, (teams + 1) // 2), teams
        )
        cards.append(
            {
                "player_id": pick.id,
                "first_name": "",
                "last_name": draft_picks.label(
                    pick, team_repo.get_name(pick.original_team_id)
                ),
                "roster_status": "pick",
                "pick_round": pick.round,
                "projected_pick": (pick.round - 1) * teams + slot,
            }
        )
    return cards


def _offer_to_gm(conn, league_id, season_id, gm, to_team_id, items, today, parent):
    """Store an offer to a team another GM runs and tell them about it."""
    my_team_id = gm["team_id"]
    trade_repo = TradeRepository(conn)
    team_name = TeamRepository(conn).get_name(to_team_id)
    if parent:
        _decide(conn, parent["id"], "countered", None)
    if trade_repo.count_pending_from(league_id, my_team_id, to_team_id):
        raise TradeError(
            f"You already have an offer out to the {team_name}. "
            "Withdraw it to make another."
        )
    if trade_repo.count_pending_from(league_id, my_team_id) >= MAX_OPEN_OFFERS:
        raise TradeError(
            f"You have {MAX_OPEN_OFFERS} offers waiting on other GMs. "
            "Withdraw one to make another."
        )

    period = ReadyCheckRepository(conn).period(league_id)["sim_period"]
    offer_id = trade_repo.create_offer(
        league_id,
        season_id,
        my_team_id,
        to_team_id,
        gm.get("id"),
        today,
        items,
        parent_id=parent["id"] if parent else None,
        expires_period=period + 1,
    )
    offer = trade_repo.get(offer_id)
    event = "counter" if parent else "offer"
    verb = "countered with" if parent else "offer"
    _notify(
        conn,
        league_id,
        to_team_id,
        event,
        offer,
        f"The {offer['from_name']} {verb} {_names(offer['sent'])} "
        f"for {_names(offer['received'])}.",
    )
    conn.commit()
    return {"pending": True, "offer_id": offer_id, "to_name": team_name}


def respond(conn, league_id: str, gm: dict, offer_id: str, action: str) -> dict:
    """The GM's answer to an offer: accept or reject one made to them, or
    withdraw one they made. Returns {"status"}, plus "arrived" once a trade
    has gone through and "voters" when it goes to the league's vote."""
    try:
        with league_lock(conn, league_id):
            return _respond(conn, league_id, gm, offer_id, action)
    except LeagueBusy:
        raise TradeError("Games are being played. Try again in a moment.")


def _respond(conn, league_id, gm, offer_id, action) -> dict:
    trade_repo = TradeRepository(conn)
    offer = trade_repo.get(offer_id)
    if not offer or offer["league_id"] != league_id:
        raise TradeError("That offer isn't in this league.")
    mine = gm["team_id"]
    if offer["status"] != "pending":
        raise TradeError("That offer has already been answered.")

    if action == "withdraw":
        if offer["from_team_id"] != mine:
            raise TradeError("Only the team that made an offer can withdraw it.")
        _decide(conn, offer_id, "withdrawn", None)
        _notify(
            conn,
            league_id,
            offer["to_team_id"],
            "withdrawn",
            offer,
            f"The {offer['from_name']} withdrew their offer for "
            f"{_names(offer['received'])}.",
        )
        conn.commit()
        return {"status": "withdrawn"}

    if offer["to_team_id"] != mine:
        raise TradeError("That offer wasn't made to you.")

    if action == "reject":
        _decide(conn, offer_id, "rejected", None)
        _notify(
            conn,
            league_id,
            offer["from_team_id"],
            "rejected",
            offer,
            f"The {offer['to_name']} turned down your offer for "
            f"{_names(offer['received'])}.",
        )
        conn.commit()
        return {"status": "rejected"}

    if action != "accept":
        raise TradeError("Accept, reject or withdraw.")

    league = dict(LeagueRepository(conn).get_by_id(league_id))
    problem = _problem(conn, league, offer)
    if problem:
        _void(conn, league_id, offer, problem)
        conn.commit()
        raise TradeError(f"This trade can't go through: {problem}")
    if offer["from_ai"] and not _ai_still_wants(conn, league_id, offer):
        reason = f"the {offer['from_name']} changed their mind."
        _void(conn, league_id, offer, reason)
        conn.commit()
        raise TradeError(f"This trade can't go through: {reason}")

    voters = _voters(conn, league, offer)
    if voters:
        period = ReadyCheckRepository(conn).period(league_id)["sim_period"]
        trade_repo.open_vote(offer_id, voters, period + 1)
        offer = trade_repo.get(offer_id)
        _notify(
            conn,
            league_id,
            offer["from_team_id"],
            "vote_open",
            offer,
            f"The {offer['to_name']} accepted your offer. "
            "It goes to a league vote before the next sim.",
        )
        desc = (
            f"The {offer['from_name']} get {_names(offer['received'])}, "
            f"the {offer['to_name']} get {_names(offer['sent'])}."
        )
        for gm_id in voters:
            _notify_gm(conn, gm_id, "vote", offer, f"Vote on a trade: {desc}")
        conn.commit()
        return {"status": "pending_vote", "voters": len(voters)}

    _complete(conn, league_id, offer)
    conn.commit()
    return {
        "status": "accepted",
        "arrived": [_name(p) for p in offer["sent"]],
        "playing_count": playing_count(conn, mine),
    }


def vote(conn, league_id: str, gm: dict, offer_id: str, yes: bool) -> dict:
    """A GM's vote on another two GMs' trade. The vote ends as soon as the
    result can't change. Returns {"status", "tally"}."""
    try:
        with league_lock(conn, league_id):
            trade_repo = TradeRepository(conn)
            offer = trade_repo.get(offer_id)
            if (
                not offer
                or offer["league_id"] != league_id
                or offer["status"] != "pending_vote"
            ):
                raise TradeError("That vote is over.")
            if not trade_repo.cast_vote(offer_id, gm["id"], yes):
                raise TradeError("You don't have a vote on this trade.")
            status = _settle_vote(conn, league_id, offer, final=False)
            conn.commit()
            return {"status": status, "tally": trade_repo.tally(offer_id)}
    except LeagueBusy:
        raise TradeError("Games are being played. Try again in a moment.")


def _voters(conn, league: dict, offer: dict) -> list[str]:
    """The GMs who vote on a trade between two GMs: every other human GM who
    isn't away. None when the league doesn't vote or it's a trade with the
    AI."""
    if not league.get("trade_vote"):
        return []
    gm_repo = GMRepository(conn)
    sides = (offer["from_team_id"], offer["to_team_id"])
    if not all(gm_repo.get_human_gm_for_team(league["id"], t) for t in sides):
        return []
    return [
        g["id"]
        for g in ReadyCheckRepository(conn).gms(league["id"])
        if g["team_id"] not in sides and not g["is_away"]
    ]


def _settle_vote(conn, league_id: str, offer: dict, final: bool) -> str:
    """Carry out or call off a trade on the league's vote once the result is
    certain, or, when final, now (a missing vote counts as no). Returns the
    offer's status."""
    t = TradeRepository(conn).tally(offer["id"])
    needed = t["voters"] // 2 + 1  # more than half
    if t["voters"] == 0 or t["yes"] >= needed:
        league = dict(LeagueRepository(conn).get_by_id(league_id))
        problem = _problem(conn, league, offer)
        if problem:
            _void(conn, league_id, offer, problem)
            _tell_waiting_voters(conn, offer, "was called off")
            return "void"
        _complete(conn, league_id, offer, by_vote=True)
        _tell_waiting_voters(conn, offer, "passed")
        return "accepted"
    if final or t["voters"] - t["no"] < needed:
        _tell_waiting_voters(conn, offer, "was voted down")
        _decide(
            conn, offer["id"], "voted_down", f"{t['yes']} of {t['voters']} voted yes"
        )
        for team, other in (
            (offer["from_team_id"], offer["to_name"]),
            (offer["to_team_id"], offer["from_name"]),
        ):
            _notify(
                conn,
                league_id,
                team,
                "voted_down",
                offer,
                f"The league voted down your trade with the {other} "
                f"({t['yes']} of {t['voters']} voted yes).",
            )
        return "voted_down"
    return "pending_vote"


def _ai_still_wants(conn, league_id: str, offer: dict) -> bool:
    """An AI team's own offer, being accepted days later: does it still come
    out ahead? (Injuries, or other trades, may have changed things.) It
    doesn't need its margin any more, only not to lose."""
    season_id = offer["season_id"]
    return ai_answer(
        conn,
        league_id,
        season_id,
        offer["from_team_id"],
        offer["to_team_id"],
        [p["player_id"] for p in offer["sent"]],
        [p["player_id"] for p in offer["received"]],
        _league_date(conn, season_id),
        margin_share=0.0,
    ).accept


def ai_offer(
    conn,
    league_id: str,
    season_id: str,
    from_team: str,
    to_team: str,
    give: list[str],
    get: list[str],
    today: str,
    expiry: dict,
) -> str:
    """An AI team's offer to a team a person runs (src/api/services/
    ai_trades.py). It pops up for them. expiry is expires_period or
    expires_on."""
    trade_repo = TradeRepository(conn)
    offer_id = trade_repo.create_offer(
        league_id,
        season_id,
        from_team,
        to_team,
        GMRepository(conn).get_gm_id_from_team_id(league_id, from_team),
        today,
        [(pid, from_team) for pid in give] + [(pid, to_team) for pid in get],
        from_ai=True,
        **expiry,
    )
    offer = trade_repo.get(offer_id)
    _notify(
        conn,
        league_id,
        to_team,
        "offer",
        offer,
        f"The {offer['from_name']} offer {_names(offer['sent'])} "
        f"for {_names(offer['received'])}.",
    )
    return offer_id


def ai_trade(
    conn,
    league_id: str,
    season_id: str,
    from_team: str,
    to_team: str,
    give: list[str],
    get: list[str],
    today: str,
) -> str:
    """A trade two AI teams agreed on: it goes through at once and shows in
    the league's trades."""
    trade_repo = TradeRepository(conn)
    offer_id = trade_repo.create_offer(
        league_id,
        season_id,
        from_team,
        to_team,
        GMRepository(conn).get_gm_id_from_team_id(league_id, from_team),
        today,
        [(pid, from_team) for pid in give] + [(pid, to_team) for pid in get],
        from_ai=True,
    )
    _decide(conn, offer_id, "accepted", None)
    execute(
        conn,
        league_id,
        season_id,
        {from_team: give, to_team: get},
        _next_game_date(conn, season_id),
    )
    return offer_id


def close_due_on(conn, league_id: str, on: str) -> None:
    """After a day's games: expire offers whose last day (expires_on) was
    this one or earlier. Run under the league lock."""
    trade_repo = TradeRepository(conn)
    for offer_id in trade_repo.pending_due_on(league_id, on):
        _expire(conn, league_id, trade_repo.get(offer_id))


def _tell_waiting_voters(conn, offer: dict, outcome: str) -> None:
    """The vote is over before everyone voted (the result couldn't change,
    or a trade in it went elsewhere): tell the GMs who hadn't voted yet."""
    for gm_id in TradeRepository(conn).waiting_voters(offer["id"]):
        _notify_gm(
            conn,
            gm_id,
            "vote_over",
            offer,
            f"The vote on the {offer['from_name']} and {offer['to_name']} trade "
            f"is over: it {outcome}.",
        )


def _problem(conn, league: dict, offer: dict) -> str | None:
    """Why an agreed trade can no longer go through, or None."""
    try:
        _check_window(conn, league, offer["season_id"])
        _check_assets(
            conn,
            league,
            offer["season_id"],
            offer["from_team_id"],
            offer["to_team_id"],
            [p["player_id"] for p in offer["sent"]],
            [p["player_id"] for p in offer["received"]],
        )
    except TradeError as e:
        return str(e)
    return None


def _complete(conn, league_id: str, offer: dict, by_vote: bool = False) -> None:
    """Carry out an agreed trade and tell both GMs."""
    _decide(conn, offer["id"], "accepted", None)
    execute(
        conn,
        league_id,
        offer["season_id"],
        {
            offer["from_team_id"]: [p["player_id"] for p in offer["sent"]],
            offer["to_team_id"]: [p["player_id"] for p in offer["received"]],
        },
        _next_game_date(conn, offer["season_id"]),
    )
    how = "The league approved your trade with" if by_vote else "Trade done with"
    for team, other, got in (
        (offer["from_team_id"], offer["to_name"], offer["received"]),
        (offer["to_team_id"], offer["from_name"], offer["sent"]),
    ):
        # The GM who accepted saw it happen, unless it waited on the vote.
        if team == offer["to_team_id"] and not by_vote:
            continue
        _notify(
            conn,
            league_id,
            team,
            "accepted",
            offer,
            f"{how} the {other}: you get {_names(got)}.",
        )


def _void(conn, league_id: str, offer: dict, reason: str) -> None:
    _decide(conn, offer["id"], "void", reason)
    for team, other in (
        (offer["from_team_id"], offer["to_name"]),
        (offer["to_team_id"], offer["from_name"]),
    ):
        _notify(
            conn,
            league_id,
            team,
            "void",
            offer,
            f"Your trade with the {other} is off: {reason}",
        )


def close_due(conn, league_id: str, period: int) -> None:
    """Before a multiplayer period runs: expire the offers whose time is up
    and close the votes that end now. Run under the league lock."""
    for offer in TradeRepository(conn).open_offers(league_id):
        if (
            offer["status"] == "pending"
            and offer["expires_period"] is not None
            and offer["expires_period"] <= period
        ):
            _expire(conn, league_id, offer)
        elif (
            offer["status"] == "pending_vote"
            and offer["vote_period"] is not None
            and offer["vote_period"] <= period
        ):
            _settle_vote(conn, league_id, offer, final=True)


def close_at_deadline(conn, league_id: str) -> None:
    """Before a sim plays past the trade deadline (or with the window already
    shut): every open offer expires and every vote closes. Run under the
    league lock."""
    league = LeagueRepository(conn).get_by_id(league_id)
    season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
    if not league or not season_id:
        return
    window = trade_deadline.window(conn, dict(league), season_id)
    if window["open"] and not window["deadline_day"]:
        return
    close_all(conn, league_id)


def close_all(conn, league_id: str) -> None:
    """Every open offer expires and every vote closes: at the deadline, and
    when the offseason starts a new season. Run under the league lock."""
    for offer in TradeRepository(conn).open_offers(league_id):
        if offer["status"] == "pending":
            _expire(conn, league_id, offer)
        else:
            _settle_vote(conn, league_id, offer, final=True)


def draft_run(conn, league_id: str, draft_year: int) -> None:
    """A draft has used its picks: call off the open offers with any in."""
    for offer in TradeRepository(conn).open_offers(league_id):
        if any(
            p.get("is_pick")
            and draft_picks.parse(p["player_id"]).draft_year == draft_year
            for p in offer["sent"] + offer["received"]
        ):
            _void(conn, league_id, offer, "the draft has used its picks.")


def _expire(conn, league_id: str, offer: dict) -> None:
    _decide(conn, offer["id"], "expired", None)
    _notify(
        conn,
        league_id,
        offer["from_team_id"],
        "expired",
        offer,
        f"Your offer to the {offer['to_name']} expired.",
    )
    _notify(
        conn,
        league_id,
        offer["to_team_id"],
        "expired",
        offer,
        f"The {_their(offer['from_name'])} offer for {_names(offer['received'])} "
        "expired.",
    )


def team_leaving(conn, league_id: str, team_id: str, gm_id: str) -> None:
    """A GM is leaving the league (their team goes to the AI): call off their
    open offers, and take them off the league's votes. Run under the league
    lock."""
    trade_repo = TradeRepository(conn)
    for offer_id in trade_repo.open_offers_for_team(league_id, team_id):
        _void(conn, league_id, trade_repo.get(offer_id), "a GM left the league.")
    for offer_id in trade_repo.drop_voter(gm_id):
        _settle_vote(conn, league_id, trade_repo.get(offer_id), final=False)


def inbox_count(conn, league_id: str, gm: dict) -> int:
    """How many offers and votes are waiting on this GM."""
    if not gm.get("team_id"):
        return 0
    trade_repo = TradeRepository(conn)
    return len(
        trade_repo.offers_to_team(league_id, gm["team_id"])
    ) + trade_repo.unvoted_count(league_id, gm["id"])


def offers_to_humans(conn, league_id: str) -> set[str]:
    """Ids of the offers waiting on a human GM: a single-player sim stops
    when a new one arrives, if the league says so."""
    teams = GMRepository(conn).get_human_team_ids(league_id)
    return TradeRepository(conn).open_to_teams(league_id, teams) if teams else set()


def _decide(conn, offer_id: str, status: str, reason: str | None) -> None:
    """Settle an offer (or move it on to the vote). A popup about it that
    a GM hasn't seen yet is dropped: there's nothing left for them to
    answer."""
    TradeRepository(conn).decide(offer_id, status, reason)
    NotificationRepository(conn).drop_trade_popups(offer_id)


def _notify(conn, league_id: str, team_id: str, event: str, offer, text) -> None:
    """Tell a team's GM, if a person runs it."""
    gm_id = GMRepository(conn).get_human_gm_for_team(league_id, team_id)
    if gm_id:
        _notify_gm(conn, gm_id, event, offer, text)


def _notify_gm(conn, gm_id: str, event: str, offer: dict, text: str) -> None:
    NotificationRepository(conn).add(
        gm_id,
        "trade",
        {
            "event": event,
            "offer_id": offer["id"],
            "text": text,
            "popup": event in POPUP_EVENTS,
        },
    )


def _their(team: str) -> str:
    """The possessive of a team name: the Falcons' offer, the Heat's."""
    return f"{team}'" if team.endswith("s") else f"{team}'s"


def _name(p: dict) -> str:
    return f"{p['first_name']} {p['last_name']}".strip()


def _names(players: list[dict]) -> str:
    return ", ".join(_name(p) for p in players)


def ai_answer(
    conn,
    league_id: str,
    season_id: str,
    ai_team_id: str,
    other_team_id: str,
    giving: list[str],
    getting: list[str],
    today: str,
    margin_share: float | None = None,
) -> ai_evaluator.Verdict:
    """The AI team's answer to giving `giving` for `getting`, wanting to win
    by margin_share (by default its margin for this team today)."""
    injuries = InjuryRepository(conn, league_id)
    roster = _assets(conn, ai_team_id, injuries.get_team_injuries(ai_team_id, today))
    theirs = _assets(
        conn, other_team_id, injuries.get_team_injuries(other_team_id, today)
    )
    by_id = {a.id: a for a in roster + theirs}
    by_id.update(_pick_assets(conn, league_id, season_id, giving + getting))
    return ai_evaluator.evaluate(
        roster=roster,
        giving=[by_id[pid] for pid in giving],
        getting=[by_id[pid] for pid in getting],
        stance=stance(conn, league_id, season_id, ai_team_id),
        days_left=_season_days_left(conn, league_id, season_id, today),
        margin_share=ai_evaluator.margin(ai_team_id, other_team_id, today)
        if margin_share is None
        else margin_share,
    )


def _pick_assets(conn, league_id: str, season_id: str, ids) -> dict[str, Asset]:
    """The draft picks among ids, as the AI sees them."""
    picks = [draft_picks.parse(i) for i in ids if draft_picks.is_pick(i)]
    if not picks:
        return {}
    team_repo = TeamRepository(conn)
    out = {}
    for pick in picks:
        slots, teams = draft_picks.projected_slots(
            conn, league_id, season_id, pick.draft_year
        )
        out[pick.id] = draft_picks.asset(
            pick,
            slots.get(pick.original_team_id, (teams + 1) // 2),
            teams,
            team_repo.get_name(pick.original_team_id),
        )
    return out


def _season_days_left(conn, league_id: str, season_id: str, today: str) -> int:
    """Days of the season left to play; in the offseason, the next one."""
    league = LeagueRepository(conn).get_by_id(league_id)
    if league and league["state"] in trade_deadline.OFFSEASON_STATES:
        return OFFSEASON_DAYS_LEFT
    return _days_left(conn, season_id, today)


def execute(
    conn,
    league_id: str,
    season_id: str,
    sides: dict[str, list[str]],
    effective_date: str,
) -> None:
    """Move each team's players and draft picks in `sides` ({team_id: ids it
    gives up}) to the other team. Two teams only."""
    (team_a, give_a), (team_b, give_b) = sides.items()
    team_repo = TeamRepository(conn)
    status_repo = PlayerStatusRepository(conn)
    since = date.fromisoformat(effective_date)
    for from_team, to_team, ids in ((team_a, team_b, give_a), (team_b, team_a, give_b)):
        players = []
        for asset_id in ids:
            pick = draft_picks.parse(asset_id)
            if pick:
                draft_picks.move(conn, league_id, pick, to_team)
                continue
            players.append(asset_id)
            team_repo.remove_player(from_team, asset_id)
            team_repo.add_player(to_team, asset_id)
            status_repo.set_status(asset_id, "minors", since=since)
        _clear_roles(conn, from_team, season_id, players, effective_date)

    gm_repo = GMRepository(conn)
    for team_id in (team_a, team_b):
        if not gm_repo.get_human_gm_for_team(league_id, team_id):
            _replan_ai_team(conn, league_id, season_id, team_id, effective_date)

    trade_repo = TradeRepository(conn)
    for offer_id in trade_repo.open_offers_with_players(league_id, give_a + give_b):
        _void(
            conn,
            league_id,
            trade_repo.get(offer_id),
            "a player or pick in it was traded.",
        )


def _clear_roles(conn, team_id, season_id, player_ids, effective_date) -> None:
    """Take traded players out of the old team's rotation, bullpen and saved
    lineup, from the next game on."""
    conn.execute(
        """UPDATE team_rotations SET end_date = %s
           WHERE team_id = %s AND season_id = %s AND end_date IS NULL
             AND player_id = ANY(%s)""",
        (effective_date, team_id, season_id, player_ids),
    )
    conn.execute(
        """UPDATE bullpen_roles SET end_date = %s
           WHERE team_id = %s AND season_id = %s AND end_date IS NULL
             AND player_id = ANY(%s)""",
        (effective_date, team_id, season_id, player_ids),
    )
    conn.execute(
        """DELETE FROM gm_lineup_preferences
           WHERE player_id = ANY(%s)
             AND gm_id IN (SELECT id FROM gms WHERE team_id = %s)""",
        (player_ids, team_id),
    )


def _replan_ai_team(conn, league_id, season_id, team_id, effective_date) -> None:
    """An AI team re-picks its 40-man and its rotation and bullpen."""
    players = PlayerRepository(conn).get_players_by_team(team_id)
    if players:
        PlayerStatusRepository(conn).bulk_set(RosterAssigner().assign(players))
    seed_ai_rotations(
        conn,
        season_id,
        {team_id},
        statuses=["26man", "40man"],
        effective_date=effective_date,
        league_id=league_id,
    )


def stance(conn, league_id: str, season_id: str, team_id: str) -> str:
    """contender, seller or neutral, from the standings. Everyone's neutral
    in the offseason: last season's race is over."""
    league = LeagueRepository(conn).get_by_id(league_id)
    if league and league["state"] in trade_deadline.OFFSEASON_STATES:
        return "neutral"
    rows = StandingsRepository(conn).get_records(league_id, season_id)
    me = next((r for r in rows if r["team_id"] == team_id), None)
    if not me:
        return "neutral"
    played = me["wins"] + me["losses"]
    if played < STANCE_MIN_GAMES or len(rows) <= PLAYOFF_SPOTS:
        return "neutral"
    ranked = sorted(rows, key=lambda r: r["losses"] - r["wins"])
    last_spot = ranked[PLAYOFF_SPOTS - 1]
    games_back = (
        (last_spot["wins"] - me["wins"]) + (me["losses"] - last_spot["losses"])
    ) / 2
    if ranked.index(me) < PLAYOFF_SPOTS or games_back <= CONTENDER_GB:
        return "contender"
    if games_back > SELLER_GB:
        return "seller"
    return "neutral"


def _assets(conn, team_id: str, injuries: dict[str, int]) -> list[Asset]:
    return [
        Asset.from_record(p, injuries.get(p.id, 0))
        for p in PlayerRepository(conn).get_players_by_team(team_id)
    ]


def _league_date(conn, season_id: str) -> str:
    """Today in the league: the last day played, or opening day before any
    games. Offers are dated with it (deadline day's trades read as deadline
    day)."""
    last = trade_deadline.last_played_date(conn, season_id)
    return last or _next_game_date(conn, season_id)


def _next_game_date(conn, season_id: str) -> str:
    """The first day a trade counts from: the next day with games."""
    row = GameRepository(conn).get_next_unplayed_date(season_id)
    if row:
        return row["game_date"]
    return trade_deadline.last_played_date(conn, season_id) or date.today().isoformat()


def _days_left(conn, season_id: str, today: str) -> int:
    row = conn.execute(
        """SELECT MAX(game_date) AS d FROM games
           WHERE season_id = %s AND series_id IS NULL""",
        (season_id,),
    ).fetchone()
    if not row or not row["d"]:
        return 1
    return max(1, (date.fromisoformat(row["d"]) - date.fromisoformat(today)).days + 1)


def _dedupe(ids: list[str]) -> list[str]:
    return list(dict.fromkeys(ids))
