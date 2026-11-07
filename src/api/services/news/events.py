# src/api/services/news/events.py
"""
Stories about the league's events rather than its days: trades, the draft,
the All-Star break, the end of the regular season (stat crowns, division
titles, how each trade worked out), the playoffs, fired GMs and notable
retirements.

Each one checks what has happened and writes its story once (the key), so
they can all run after every sim job.
"""

from __future__ import annotations

from src.api.services import all_star as all_star_service
from src.api.services import awards as awards_service
from src.api.services import hall_of_fame as hof_service
from src.api.services.career import ROUND_OF_SERIES, _finishes
from src.api.services.news.names import Names, and_list, is_deadline_deal, possessive
from src.db.repositories.news_repo import NewsRepository
from src.league import awards as awards_mod
from src.league import divisions, swing_off

# ── Trades ────────────────────────────────────────────────────────────────────


def trades(conn, names: Names, league_id: str, season_ids: list[str]) -> None:
    """A story for each accepted trade in these seasons without one yet."""
    news = NewsRepository(conn)
    offers = conn.execute(
        """SELECT o.id, o.season_id, o.from_team_id, o.to_team_id, o.from_gm_id,
                  o.created_on, o.from_ai
           FROM trade_offers o
           WHERE o.league_id = %s AND o.status = 'accepted'
             AND o.season_id = ANY(%s)
             AND NOT EXISTS (SELECT 1 FROM league_news n
                             WHERE n.league_id = o.league_id
                               AND n.key = 'trade:' || o.id)
           ORDER BY o.created_on, o.created_at""",
        (league_id, season_ids),
    ).fetchall()
    for o in offers:
        sides = _trade_sides(conn, names, o)
        a, b = o["from_team_id"], o["to_team_id"]
        gm_a = names.gm(o["from_gm_id"]) or names.gm_of(a)
        gm_b = names.gm_of(b)
        got_a, got_b = sides[a], sides[b]
        deadline = is_deadline_deal(conn, o["season_id"], o["created_on"])
        lead = _lead(names, a, gm_a, got_a, b)
        headline = ("Deadline deal: " if deadline else "") + lead
        body = (
            f"The {names.full_team(a)} get {and_list(got_a) or 'nothing'};"
            f" the {names.full_team(b)} get {and_list(got_b) or 'nothing'}."
        )
        if gm_a and gm_b and not gm_b["is_ai"] and not gm_a["is_ai"]:
            body += f" A deal between {names.gm_name(gm_a)} and {names.gm_name(gm_b)}."
        human = names.is_human(a) or names.is_human(b)
        news.add(
            league_id, o["season_id"], o["created_on"], "trade", f"trade:{o['id']}",
            headline, body,
            weight=3 if deadline and human else 2,
            team_ids=[a, b],
            player_ids=_trade_player_ids(conn, o["id"]),
            gm_ids=[g["id"] for g in (gm_a, gm_b) if g],
        )  # fmt: skip


def _lead(names: Names, a: str, gm_a: dict | None, got_a: list[str], b: str) -> str:
    """ "Josh's Captains land Ruiz from Tokyo" """
    what = (
        got_a[0] if len(got_a) == 1 else f"{len(got_a)} players" if got_a else "picks"
    )
    if got_a and len(got_a) == 1 and "pick" not in got_a[0]:
        what = got_a[0]
    who = (
        f"{possessive(names.gm_name(gm_a))} {names.team(a)}" if gm_a else names.team(a)
    )
    return f"{who} land {what} from the {names.team(b)}"


def _trade_sides(conn, names: Names, offer: dict) -> dict[str, list[str]]:
    """What each team got: team_id -> names of players and picks."""
    a, b = offer["from_team_id"], offer["to_team_id"]
    got: dict[str, list[str]] = {a: [], b: []}
    for r in conn.execute(
        """SELECT i.player_id, i.from_team_id FROM trade_offer_items i
           WHERE i.offer_id = %s""",
        (offer["id"],),
    ).fetchall():
        to = b if r["from_team_id"] == a else a
        got[to].append(names.player(r["player_id"]))
    for r in conn.execute(
        """SELECT draft_year, round, original_team_id, from_team_id
           FROM trade_offer_picks WHERE offer_id = %s
           ORDER BY draft_year, round""",
        (offer["id"],),
    ).fetchall():
        to = b if r["from_team_id"] == a else a
        got[to].append(
            f"{possessive(names.city(r['original_team_id']))} {r['draft_year']}"
            f" round {r['round']} pick"
        )
    return got


def _trade_player_ids(conn, offer_id: str) -> list[str]:
    return [
        r["player_id"]
        for r in conn.execute(
            "SELECT player_id FROM trade_offer_items WHERE offer_id = %s", (offer_id,)
        ).fetchall()
    ]


# ── The draft ─────────────────────────────────────────────────────────────────


def drafts(conn, names: Names, league_id: str, season_ids: list[str]) -> None:
    """The first overall pick, and each person's first pick, once a draft is
    complete."""
    news = NewsRepository(conn)
    for d in conn.execute(
        """SELECT d.id, d.season_id, s.year FROM drafts d
           JOIN seasons s ON s.id = d.season_id
           WHERE d.league_id = %s AND d.state = 'complete'
             AND d.season_id = ANY(%s)""",
        (league_id, season_ids),
    ).fetchall():
        if news.has(league_id, f"draft:{d['id']}"):
            continue
        picks = conn.execute(
            """SELECT dp.pick_number, dp.round, dp.team_id, dp.gm_id, dp.player_id,
                      p.position
               FROM draft_picks dp JOIN players p ON p.id = dp.player_id
               WHERE dp.draft_id = %s ORDER BY dp.pick_number""",
            (d["id"],),
        ).fetchall()
        if not picks:
            continue
        names.load_players(p["player_id"] for p in picks)
        on = f"{d['year']}-03-22"
        first = picks[0]
        gm = names.gm(first["gm_id"])
        who = names.player(first["player_id"])
        pos = f" ({first['position'].upper()})" if first["position"] else ""
        news.add(
            league_id, d["season_id"], on, "draft", f"draft:{d['id']}",
            f"{names.team(first['team_id'])} take {who} first overall",
            f"{who}{pos} goes No. 1 in the {d['year']} draft"
            + (f", the pick of {names.gm_name(gm)}." if gm else "."),
            weight=3, team_ids=[first["team_id"]], player_ids=[first["player_id"]],
            gm_ids=[gm["id"]] if gm else [],
        )  # fmt: skip
        seen: set[str] = {first["team_id"]}
        for p in picks[1:]:
            if p["team_id"] in seen:
                continue
            seen.add(p["team_id"])
            gm = names.gm(p["gm_id"])
            if not gm or gm["is_ai"]:
                continue
            who = names.player(p["player_id"])
            pos = f" ({p['position'].upper()})" if p["position"] else ""
            news.add(
                league_id, d["season_id"], on, "draft",
                f"draft:{d['id']}:{p['team_id']}",
                f"{names.gm_name(gm)} picks {who} for the {names.team(p['team_id'])}",
                f"{who}{pos} is {possessive('the ' + names.team(p['team_id']))} first pick in the"
                f" {d['year']} draft, No. {p['pick_number']} overall.",
                weight=2, team_ids=[p["team_id"]], player_ids=[p["player_id"]],
                gm_ids=[gm["id"]],
            )  # fmt: skip


# ── The All-Star break ────────────────────────────────────────────────────────


def _count_word(n: int) -> str:
    return {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}.get(n, str(n))


def _all_star_team_body(
    names: Names, team: str, pids: list[str], hurt: set, stand_in: dict, team_of: dict
) -> str:
    """A GM's All-Stars: who made it, who's hurt and who takes his place,
    and who's in as a reserve for someone else's injured All-Star."""

    def of(pid: str) -> str:
        t = team_of.get(pid)
        return f" of the {names.team(t)}" if t and t != team else ""

    reserve_for = {s["player_id"]: r for r, s in stand_in.items()}
    voted = [p for p in pids if p not in reserve_for]
    reserves = [p for p in pids if p in reserve_for]
    parts = []
    if voted:
        many = len(voted) > 1
        parts.append(
            f"{and_list([names.player(p) for p in voted])}"
            f" {'are All-Stars' if many else 'is an All-Star'}."
        )
    for p in voted:
        if p not in hurt:
            continue
        sub = stand_in.get(p)
        if sub:
            parts.append(
                f"{names.last(p)} is injured; {names.player(sub['player_id'])}"
                f"{of(sub['player_id'])} takes his place."
            )
        else:
            parts.append(f"{names.last(p)} is injured and will miss the game.")
    for p in reserves:
        gone = reserve_for[p]
        if team_of.get(gone) == team:
            continue  # said above
        parts.append(
            f"{names.player(p)} is in as a reserve for the injured"
            f" {names.player(gone)}{of(gone)}."
        )
    credits = [
        f"{names.last(p)} ({how})" for p in pids if (how := names.origin(p, team)[0])
    ]
    if credits:
        parts.append(f"{and_list(credits)}.")
    return " ".join(parts)


def all_stars(conn, names: Names, league_id: str, season_id: str) -> None:
    news = NewsRepository(conn)
    rows = conn.execute(
        """SELECT a.player_id, a.team_id, a.replaces FROM all_stars a
           WHERE a.season_id = %s
           ORDER BY a.points DESC, a.score DESC, a.player_id""",
        (season_id,),
    ).fetchall()
    if not rows:
        return
    w = all_star_service.window(conn, season_id)
    on = w.closes if w else _now(conn, season_id)
    names.load_players(r["player_id"] for r in rows)
    if not news.has(league_id, f"allstar:roster:{season_id}"):
        by_team: dict[str, list[str]] = {}
        for r in rows:
            by_team.setdefault(r["team_id"], []).append(r["player_id"])
        top = max(by_team, key=lambda t: len(by_team[t]))
        # The All-Stars each GM drafted, wherever they play now.
        drafted_by: dict[str, list[str]] = {}
        for r in rows:
            pick = names.drafted(r["player_id"])
            if pick and pick["gm_id"]:
                drafted_by.setdefault(pick["gm_id"], []).append(r["player_id"])
        body = (
            f"The {names.full_team(top)} lead the way with {len(by_team[top])}"
            f" All-Stars."
        )
        best_scout = max(drafted_by, key=lambda g: len(drafted_by[g]), default=None)
        if best_scout and len(drafted_by[best_scout]) >= 2 and names.gm(best_scout):
            body += (
                f" {names.gm_name(names.gm(best_scout))} drafted"
                f" {len(drafted_by[best_scout])} of them."
            )
        news.add(
            league_id, season_id, on, "all_star", f"allstar:roster:{season_id}",
            "All-Star rosters are set", body, weight=3,
            team_ids=[top], gm_ids=names.gm_ids(top),
        )  # fmt: skip
        # Who's hurt: anyone a reserve stands in for, and anyone hurt now
        # (a reserve isn't named when nobody healthy is left at his spot).
        stand_in = {r["replaces"]: r for r in rows if r["replaces"]}
        hurt = set(stand_in) | all_star_service._hurt(
            conn, league_id, [r["player_id"] for r in rows]
        )
        team_of = {r["player_id"]: r["team_id"] for r in rows}
        reserves_ids = {r["player_id"] for r in stand_in.values()}
        for team, pids in by_team.items():
            if not names.is_human(team):
                continue
            gm = names.gm_of(team)
            body = _all_star_team_body(names, team, pids, hurt, stand_in, team_of)
            n = len(pids)
            # Voted in and hurt (a reserve hurt since doesn't count).
            injured = sum(1 for p in pids if p in hurt and p not in reserves_ids)
            headline = (
                f"{possessive(names.gm_name(gm))} {names.team(team)} send"
                f" {n} to the All-Star Game"
            )
            if injured == n:
                headline += ", but he's injured" if n == 1 else ", all injured"
            elif injured:
                headline += f", {_count_word(injured)} injured"
            news.add(
                league_id, season_id, on, "all_star",
                f"allstar:team:{season_id}:{team}", headline,
                body, weight=2, team_ids=[team], player_ids=pids, gm_ids=[gm["id"]],
            )  # fmt: skip
    g = conn.execute(
        """SELECT * FROM all_star_games WHERE season_id = %s AND state = 'played'""",
        (season_id,),
    ).fetchone()
    if g and not news.has(league_id, f"allstar:game:{season_id}"):
        winner = swing_off.winner(g)
        cap_w = g[f"captain{winner}_team_id"]
        cap_l = g[f"captain{3 - winner}_team_id"]
        hi, lo = (
            max(g["score1"] or 0, g["score2"] or 0),
            min(g["score1"] or 0, g["score2"] or 0),
        )
        if g["swingoff"]:
            so = g["swingoff"]
            headline = (
                f"Team {names.city(cap_w)} wins the All-Star Game"
                " in a home run swing-off"
            )
            body = (
                f"Team {names.city(cap_w)} and Team {names.city(cap_l)} were"
                f" tied {hi}-{lo} after nine. Team {names.city(cap_w)} won the"
                f" swing-off {swing_off.total(so, winner)}-"
                f"{swing_off.total(so, 3 - winner)}."
            )
        else:
            headline = f"Team {names.city(cap_w)} wins the All-Star Game {hi}-{lo}"
            body = f"Team {names.city(cap_w)} beat Team {names.city(cap_l)}."
        players = []
        if g["mvp_player_id"]:
            mvp = g["mvp_player_id"]
            players.append(mvp)
            team = _team_of(conn, mvp, season_id)
            body += f" {names.player(mvp)} of the {names.team(team)} was named MVP."
            how, _ = names.origin(mvp, team) if team else ("", [])
            if how:
                body += f" {names.last(mvp)} was {how}."
        news.add(
            league_id, season_id, g["game_date"] or on, "all_star",
            f"allstar:game:{season_id}", headline, body, weight=2,
            team_ids=[cap_w, cap_l], player_ids=players,
            gm_ids=names.gm_ids(cap_w, cap_l),
        )  # fmt: skip
    derby = conn.execute(
        """SELECT player_id, team_id, homers FROM hr_derby_results
           WHERE season_id = %s AND won
             AND round = (SELECT MAX(round) FROM hr_derby_results WHERE season_id = %s)
           LIMIT 1""",
        (season_id, season_id),
    ).fetchone()
    if derby and not news.has(league_id, f"allstar:derby:{season_id}"):
        who = names.player(derby["player_id"])
        news.add(
            league_id, season_id, (g["game_date"] if g else None) or on, "all_star",
            f"allstar:derby:{season_id}",
            f"{who} wins the Home Run Derby",
            f"{who} of the {names.team(derby['team_id'])} hit {derby['homers']}"
            f" in the final round.",
            weight=1, team_ids=[derby["team_id"]], player_ids=[derby["player_id"]],
            gm_ids=names.gm_ids(derby["team_id"]),
        )  # fmt: skip


def _team_of(conn, player_id: str, season_id: str) -> str | None:
    row = conn.execute(
        "SELECT team_id FROM all_stars WHERE season_id = %s AND player_id = %s",
        (season_id, player_id),
    ).fetchone()
    if row:
        return row["team_id"]
    row = conn.execute(
        "SELECT team_id FROM team_players WHERE player_id = %s LIMIT 1", (player_id,)
    ).fetchone()
    return row["team_id"] if row else None


# ── End of the regular season ─────────────────────────────────────────────────


def season_end(conn, names: Names, league_id: str, season_id: str, on: str) -> None:
    """Stat crowns, division titles and trade verdicts. Call once the
    regular season is over; ``on`` is its last day."""
    news = NewsRepository(conn)
    _crowns(conn, news, names, league_id, season_id, on)
    _division_titles(conn, news, names, league_id, season_id, on)
    _trade_verdicts(conn, news, names, league_id, season_id, on)


# (key, headline noun, SQL value, order, qualifying, format)
_CROWNS = (
    # The batting, ERA and wins titles are season awards (Batting, ERA and
    # Wins Champion, src/league/awards.py), with stories of their own below.
    ("hr", "home run crown", "SUM(bat_home_runs)", "DESC", "TRUE", "{:.0f} HR"),
)  # fmt: skip


def _crowns(conn, news, names, league_id, season_id, on) -> None:
    games = conn.execute(
        """SELECT COALESCE(MAX(n), 0) AS games FROM (
               SELECT COUNT(*) AS n FROM team_game_stats tgs
               JOIN games g ON g.id = tgs.game_id
               WHERE g.season_id = %s AND g.series_id IS NULL AND g.completed = 1
               GROUP BY tgs.team_id) t""",
        (season_id,),
    ).fetchone()["games"]
    for key, noun, value, order, qualifies, fmt in _CROWNS:
        if news.has(league_id, f"crown:{key}:{season_id}"):
            continue
        row = conn.execute(
            f"""SELECT player_id,
                       (ARRAY_AGG(team_id ORDER BY bat_games_played + pitch_games_played DESC))[1] AS team_id,
                       {value} AS value
                FROM player_season_stats
                WHERE season_id = %(season)s AND NOT is_postseason
                GROUP BY player_id
                HAVING {value} IS NOT NULL AND {qualifies}
                ORDER BY value {order} LIMIT 1""",
            {"season": season_id, "games": games},
        ).fetchone()
        if not row or row["value"] is None:
            continue
        pid, team = (
            row["player_id"],
            _current_team(conn, row["player_id"]) or row["team_id"],
        )
        who = names.player(pid)
        stat = fmt.format(row["value"])
        body = f"{who} of the {names.full_team(team)} finished with {stat}."
        how, credit = names.origin(pid, team)
        if how:
            body += f" {names.last(pid)} was {how}."
        news.add(
            league_id, season_id, on, "award", f"crown:{key}:{season_id}",
            f"{who} wins the {noun}", body, weight=2,
            team_ids=[team], player_ids=[pid], gm_ids=names.gm_ids(team) + credit,
        )  # fmt: skip


def _current_team(conn, player_id: str) -> str | None:
    row = conn.execute(
        "SELECT team_id FROM team_players WHERE player_id = %s LIMIT 1", (player_id,)
    ).fetchone()
    return row["team_id"] if row else None


def _division_titles(conn, news, names, league_id, season_id, on) -> None:
    confs = divisions.load(conn, league_id)
    if not confs:
        return
    finish = _finishes(conn, league_id, season_id)
    records = {
        r["team_id"]: (r["wins"], r["losses"])
        for r in conn.execute(
            """SELECT tgs.team_id, SUM(tgs.win) AS wins, SUM(tgs.loss) AS losses
               FROM team_game_stats tgs JOIN games g ON g.id = tgs.game_id
               WHERE g.season_id = %s AND g.series_id IS NULL AND g.completed = 1
               GROUP BY tgs.team_id""",
            (season_id,),
        ).fetchall()
    }
    last_year = _previous_records(conn, league_id, season_id)
    for conf in confs:
        for div in conf.divisions:
            winner = next(
                (t for t in div.team_ids if finish.get(t, (0,))[0] == 1), None
            )
            if not winner:
                continue
            w, l = records.get(winner, (0, 0))
            gm = names.gm_name(names.gm_of(winner))
            headline = f"{names.team(winner)} win the {div.name}"
            body = f"The {names.full_team(winner)} finished {w}-{l}"
            prev = last_year.get(winner)
            if prev and prev[0] < prev[1]:
                body += f", up from {prev[0]}-{prev[1]} last season"
            body += "."
            if gm:
                body += f" A division title for {gm}."
            news.add(
                league_id, season_id, on, "division", f"division:{season_id}:{winner}",
                headline, body, weight=2,
                team_ids=[winner], gm_ids=names.gm_ids(winner),
            )  # fmt: skip


def _previous_records(conn, league_id, season_id) -> dict[str, tuple[int, int]]:
    prev = conn.execute(
        """SELECT s.id FROM seasons s JOIN league_seasons ls ON ls.season_id = s.id
           WHERE ls.league_id = %s
             AND s.year < (SELECT year FROM seasons WHERE id = %s)
           ORDER BY s.year DESC LIMIT 1""",
        (league_id, season_id),
    ).fetchone()
    if not prev:
        return {}
    return {
        r["team_id"]: (r["wins"], r["losses"])
        for r in conn.execute(
            """SELECT tgs.team_id, SUM(tgs.win) AS wins, SUM(tgs.loss) AS losses
               FROM team_game_stats tgs JOIN games g ON g.id = tgs.game_id
               WHERE g.season_id = %s AND g.series_id IS NULL AND g.completed = 1
               GROUP BY tgs.team_id""",
            (prev["id"],),
        ).fetchall()
    }


# How a player did for his new team after a trade.
PAYOFF_PA, PAYOFF_OUTS = 80, 90  # enough to judge: about 80 PA, 30 IP


def _trade_verdicts(conn, news, names, league_id, season_id, on) -> None:
    """For each trade made during the season: did it pay off?"""
    offers = conn.execute(
        """SELECT id, from_team_id, to_team_id, from_gm_id, created_on
           FROM trade_offers
           WHERE league_id = %s AND season_id = %s AND status = 'accepted'
             AND created_on <= %s""",
        (league_id, season_id, on),
    ).fetchall()
    for o in offers:
        if news.has(league_id, f"verdict:{o['id']}"):
            continue
        items = conn.execute(
            "SELECT player_id, from_team_id FROM trade_offer_items WHERE offer_id = %s",
            (o["id"],),
        ).fetchall()
        a, b = o["from_team_id"], o["to_team_id"]
        gm_by_team = {a: names.gm(o["from_gm_id"]) or names.gm_of(a), b: names.gm_of(b)}
        judged = []
        for it in items:
            to = b if it["from_team_id"] == a else a
            line = _after_trade(conn, season_id, it["player_id"], to, o["created_on"])
            if line:
                judged.append((it["player_id"], to, line))
        if not judged:
            continue
        hits = [j for j in judged if j[2]["grade"] == "hit"]
        flops = [j for j in judged if j[2]["grade"] == "flop"]
        if not hits and not flops:
            continue
        deadline = is_deadline_deal(conn, season_id, o["created_on"])
        deal = "deadline deal" if deadline else "trade"
        if hits:
            pid, to, line = max(hits, key=lambda j: j[2]["score"])
            other = a if to == b else b
            gm = gm_by_team[to]
            who = names.player(pid)
            headline = (
                f"{possessive(names.gm_name(gm))} {deal} for {names.last(pid)} pays off"
                if gm
                else f"{possessive('The ' + names.team(to))} {deal} for {names.last(pid)} pays off"
            )
            body = f"{who} {line['text']} for the {names.team(to)} after the trade"
            # The other side's record since the deal: how the team that let
            # him go fared without him.
            rec = _record_after(conn, season_id, other, o["created_on"])
            if rec:
                body += f", while the {names.team(other)} went {rec[0]}-{rec[1]}"
            body += "."
            other_gm = gm_by_team[other]
            if not any(j[1] == other for j in hits) and other_gm:
                body += f" {names.gm_name(other_gm)} may want that one back."
            team_ids = [to, other]
        else:
            pid, to, line = min(flops, key=lambda j: j[2]["score"])
            other = a if to == b else b
            gm = gm_by_team[to]
            who = names.player(pid)
            headline = (
                f"{possessive(names.gm_name(gm))} {deal} for {names.last(pid)} falls flat"
                if gm
                else f"{possessive('The ' + names.team(to))} {deal} for {names.last(pid)} falls flat"
            )
            body = f"{who} {line['text']} for the {names.team(to)} after the trade."
            team_ids = [to, other]
        human = any(names.is_human(t) for t in team_ids)
        news.add(
            league_id, season_id, on, "verdict", f"verdict:{o['id']}",
            headline, body, weight=3 if human else 2,
            team_ids=team_ids, player_ids=[pid],
            gm_ids=[g["id"] for g in gm_by_team.values() if g],
        )  # fmt: skip


def _after_trade(conn, season_id, player_id, team_id, since) -> dict | None:
    """The player's line for ``team_id`` in regular season games after
    ``since``, graded "hit", "flop" or "fine"; None with too little to go on."""
    r = conn.execute(
        """SELECT SUM(COALESCE(bat_ab, 0)) AS ab, SUM(COALESCE(bat_hits, 0)) AS h,
                  SUM(COALESCE(bat_doubles, 0)) AS d, SUM(COALESCE(bat_triples, 0)) AS t,
                  SUM(COALESCE(bat_home_runs, 0)) AS hr, SUM(COALESCE(bat_walks, 0)) AS bb,
                  SUM(COALESCE(bat_hbp, 0)) AS hbp, SUM(COALESCE(bat_sac_flys, 0)) AS sf,
                  SUM(COALESCE(bat_rbi, 0)) AS rbi,
                  SUM(COALESCE(pitch_outs, 0)) AS outs,
                  SUM(COALESCE(pitch_earned_runs, 0)) AS er,
                  SUM(COALESCE(pitch_win, 0)) AS w, SUM(COALESCE(pitch_save, 0)) AS sv
           FROM player_game_stats pgs JOIN games g ON g.id = pgs.game_id
           WHERE pgs.player_id = %s AND pgs.team_id = %s AND g.season_id = %s
             AND g.series_id IS NULL AND g.completed = 1 AND g.game_date > %s""",
        (player_id, team_id, season_id, since),
    ).fetchone()
    if not r:
        return None
    ab, h, bb = r["ab"] or 0, r["h"] or 0, r["bb"] or 0
    pa = ab + bb + (r["hbp"] or 0) + (r["sf"] or 0)
    outs = r["outs"] or 0
    if outs >= PAYOFF_OUTS and outs / 3 >= pa / 4:
        era = (r["er"] or 0) * 27 / outs
        ip = outs // 3
        text = f"posted a {era:.2f} ERA over {ip} innings"
        if r["w"]:
            text += f" with {r['w']} wins"
        elif r["sv"]:
            text += f" with {r['sv']} saves"
        grade = "hit" if era <= 3.00 else "flop" if era >= 5.50 else "fine"
        return {"grade": grade, "score": -era, "text": text}
    if pa >= PAYOFF_PA:
        singles = h - (r["d"] or 0) - (r["t"] or 0) - (r["hr"] or 0)
        tb = singles + 2 * (r["d"] or 0) + 3 * (r["t"] or 0) + 4 * (r["hr"] or 0)
        obp = (h + bb + (r["hbp"] or 0)) / pa if pa else 0
        slg = tb / ab if ab else 0
        ops = obp + slg
        avg = f"{h / ab:.3f}".replace("0.", ".") if ab else ".000"
        text = f"hit {avg} with {r['hr']} HR and {r['rbi']} RBI"
        grade = (
            "hit"
            if ops >= 0.850 or (r["hr"] or 0) >= 12
            else "flop"
            if ops < 0.600
            else "fine"
        )
        return {"grade": grade, "score": ops, "text": text}
    return None


def _record_after(conn, season_id, team_id, since) -> tuple[int, int] | None:
    r = conn.execute(
        """SELECT SUM(tgs.win) AS w, SUM(tgs.loss) AS l
           FROM team_game_stats tgs JOIN games g ON g.id = tgs.game_id
           WHERE tgs.team_id = %s AND g.season_id = %s AND g.series_id IS NULL
             AND g.completed = 1 AND g.game_date > %s""",
        (team_id, season_id, since),
    ).fetchone()
    if not r or r["w"] is None:
        return None
    return r["w"], r["l"]


# ── The playoffs ──────────────────────────────────────────────────────────────

ROUND_NAMES = {"Round 1": "first round", "Semifinals": "semifinals", "Finals": "Finals"}


def playoffs(conn, names: Names, league_id: str, season_id: str, year: int) -> None:
    """A story for each finished series, and the champion."""
    news = NewsRepository(conn)
    rows = conn.execute(
        """SELECT s.id, s.name, g.winner_id, g.home_team_id, g.away_team_id, g.game_date
           FROM series s JOIN games g ON g.series_id = s.id
           WHERE s.season_id = %s AND g.completed = 1 AND g.winner_id IS NOT NULL
           ORDER BY s.id, g.game_date, g.id""",
        (season_id,),
    ).fetchall()
    by_series: dict[str, list[dict]] = {}
    for r in rows:
        by_series.setdefault(r["id"], []).append(dict(r))
    for sid, games_in in by_series.items():
        name = games_in[0]["name"]
        rnd = ROUND_OF_SERIES.get(name)
        if not rnd or news.has(league_id, f"series:{sid}"):
            continue
        needed = 3 if rnd == "Round 1" else 4
        # Play the series back game by game until someone has the wins it
        # takes; that's the result, and the day it was won.
        wins: dict[str, int] = {}
        clinched = None
        for g in games_in:
            for t in (g["home_team_id"], g["away_team_id"]):
                wins.setdefault(t, 0)
            wins[g["winner_id"]] += 1
            if wins[g["winner_id"]] >= needed:
                clinched = g
                break
        if not clinched:
            continue
        w_id = clinched["winner_id"]
        loser = next((t for t in wins if t != w_id), None)
        lost = wins.get(loser, 0)
        winner = {"wins": wins[w_id]}
        on = clinched["game_date"]
        if rnd == "Finals":
            gm = names.gm_name(names.gm_of(w_id))
            headline = (
                f"{possessive(gm)} {names.team(w_id)} win the {year} championship"
                if gm
                else f"{names.team(w_id)} win the {year} championship"
            )
            body = f"The {names.full_team(w_id)} beat the {names.team(loser)} {winner['wins']}-{lost} in the Finals."
            if gm:
                body += f" A title for {gm}."
            weight, kind = 3, "champion"
        else:
            sweep = lost == 0
            verb = "sweep" if sweep else "beat"
            headline = f"{names.team(w_id)} {verb} the {names.team(loser)}"
            if not sweep:
                headline += f" {winner['wins']}-{lost}"
            headline += f" in the {ROUND_NAMES[rnd]}"
            body = f"The {names.full_team(w_id)} move on"
            body += " to the Finals." if rnd == "Semifinals" else "."
            loser_gm = names.gm_name(names.gm_of(loser))
            if loser_gm and names.is_human(loser):
                body += f" The season is over for {loser_gm}."
            weight, kind = (2 if rnd == "Semifinals" else 1), "series"
            if names.is_human(w_id) or names.is_human(loser):
                weight = min(3, weight + 1)
        news.add(
            league_id, season_id, on, kind, f"series:{sid}", headline, body,
            weight=weight, team_ids=[w_id, loser], gm_ids=names.gm_ids(w_id, loser),
        )  # fmt: skip


# ── Season awards ─────────────────────────────────────────────────────────────

# Awards with a story of their own; the rest share a roundup.
_FEATURED = ("mvp", "cy_young", "roy", "gm_of_year")
_FEATURED_WEIGHT = {"mvp": 3, "cy_young": 3, "roy": 2, "gm_of_year": 2}
# Awards in stories of their own: the position awards and the series MVPs.
_OWN_STORIES = (
    "gold_glove", "platinum_glove", "silver_slugger", "semis_mvp", "finals_mvp",
)  # fmt: skip


def season_awards(
    conn, names: Names, league_id: str, season_id: str, year: int
) -> None:
    """A story for each of the big awards (both leagues' winners together),
    a roundup of the rest, and one for each series MVP."""
    news = NewsRepository(conn)
    rows = awards_service.for_season(conn, season_id)
    if not rows:
        return
    names.load_players(r["player_id"] for r in rows if r["player_id"])
    by_award: dict[str, list[dict]] = {}
    for r in rows:
        by_award.setdefault(r["award"], []).append(r)

    for key in _FEATURED:
        wins = by_award.get(key)
        story = f"award:{key}:{season_id}"
        if not wins or news.has(league_id, story):
            continue
        award = awards_mod.BY_KEY[key]
        if key == "gm_of_year":
            who = [
                names.gm_name(names.gm(r["gm_id"])) or names.team(r["team_id"])
                for r in wins
            ]
            gm_ids = [r["gm_id"] for r in wins if r["gm_id"]]
            players: list[str] = []
            body = "\n".join(
                f"{w} of the {names.full_team(r['team_id'])} is the"
                f" {_scope_phrase(r['scope'])}GM of the Year ({r['line']})."
                for w, r in zip(who, wins)
            )
            human = any((g := names.gm(r["gm_id"])) and not g["is_ai"] for r in wins)
        else:
            who = [names.player(r["player_id"]) for r in wins]
            players = [r["player_id"] for r in wins]
            parts, gm_ids = [], []
            for w, r in zip(who, wins):
                text = (
                    f"{w} of the {names.full_team(r['team_id'])} wins the"
                    f" {_scope_phrase(r['scope'])}{award.name} ({r['line']})."
                )
                how, credit = names.origin(r["player_id"], r["team_id"])
                if how:
                    text += f" {names.last(r['player_id'])} was {how}."
                gm_ids += names.gm_ids(r["team_id"]) + credit
                parts.append(text)
            body = "\n".join(parts)
            human = any(names.is_human(r["team_id"]) for r in wins)
        if len(wins) == 1:
            headline = f"{who[0]} is the {year} {award.name}"
        else:
            headline = f"{and_list(who)} win the {year} {award.name} awards"
        if key == "gm_of_year" and len(wins) > 1:
            headline = f"{and_list(who)} are the {year} GMs of the Year"
        news.add(
            league_id, season_id, wins[0]["decided_on"] or _now(conn, season_id),
            "season_award", story, headline, body,
            weight=_FEATURED_WEIGHT[key] + (1 if human else 0),
            team_ids=[r["team_id"] for r in wins], player_ids=players, gm_ids=gm_ids,
        )  # fmt: skip

    story = f"award:roundup:{season_id}"
    rest = [
        r
        for r in rows
        if r["award"] not in _FEATURED and r["award"] not in _OWN_STORIES
    ]
    if rest and not news.has(league_id, story):
        lines = [
            f"{_scope_phrase(r['scope'])}{awards_mod.BY_KEY[r['award']].name}:"
            f" {names.player(r['player_id'])}, {names.team(r['team_id'])} ({r['line']})."
            for r in rest
        ]
        news.add(
            league_id, season_id, rest[0]["decided_on"] or _now(conn, season_id),
            "season_award", story, f"The rest of the {year} awards",
            "\n".join(lines),
            weight=2 if any(names.is_human(r["team_id"]) for r in rest) else 1,
            team_ids=list(dict.fromkeys(r["team_id"] for r in rest)),
            player_ids=[r["player_id"] for r in rest],
            gm_ids=names.gm_ids(*dict.fromkeys(r["team_id"] for r in rest)),
        )  # fmt: skip

    _position_story(
        conn, news, names, league_id, season_id, year, "gloves",
        by_award.get("platinum_glove", []) + by_award.get("gold_glove", []),
        "Gold Gloves",
    )  # fmt: skip
    _position_story(
        conn, news, names, league_id, season_id, year, "sluggers",
        by_award.get("silver_slugger", []), "Silver Sluggers",
    )  # fmt: skip

    for r in by_award.get("semis_mvp", []) + by_award.get("finals_mvp", []):
        story = f"award:{r['award']}:{r['scope']}:{season_id}"
        if news.has(league_id, story):
            continue
        finals = r["award"] == "finals_mvp"
        who = names.player(r["player_id"])
        team = r["team_id"]
        round_name = "Finals" if finals else "semifinals"
        news.add(
            league_id, season_id, r["decided_on"] or _now(conn, season_id),
            "season_award", story,
            f"{who} named {_scope_phrase(r['scope'])}{awards_mod.BY_KEY[r['award']].name}",
            f"{who} went {r['line']} as the {names.full_team(team)} won the"
            f" {round_name}.",
            weight=(2 if finals else 1) + (1 if names.is_human(team) else 0),
            team_ids=[team], player_ids=[r["player_id"]], gm_ids=names.gm_ids(team),
        )  # fmt: skip


def _position_story(
    conn, news, names, league_id, season_id, year, key, rows, title
) -> None:
    """One story for a position award (Gold Gloves with the Platinum Glove
    first, or Silver Sluggers): each winner and his position, a league at
    a time."""
    story = f"award:{key}:{season_id}"
    if not rows or news.has(league_id, story):
        return
    parts = []
    for r in rows:
        pos = awards_mod.POSITION_NAMES.get(r["position"], "")
        who = f"{names.player(r['player_id'])} ({names.team(r['team_id'])})"
        if r["award"] == "platinum_glove":
            parts.append(f"{_scope_phrase(r['scope'])}Platinum Glove: {who}, {pos}.")
        else:
            parts.append(f"{_scope_phrase(r['scope'])}{pos}: {who}.")
    human = [r for r in rows if names.is_human(r["team_id"])]
    headline = f"The {year} {title}"
    if human:
        gm = names.gm_name(names.gm_of(human[0]["team_id"]))
        n = len({r["player_id"] for r in human if r["award"] != "platinum_glove"})
        if gm and n:
            headline += f": {n} for {possessive(gm)} {names.team(human[0]['team_id'])}"
    teams = list(dict.fromkeys(r["team_id"] for r in rows))
    news.add(
        league_id, season_id, rows[0]["decided_on"] or _now(conn, season_id),
        "season_award", story, headline, "\n".join(parts),
        weight=2 if human else 1, team_ids=teams,
        player_ids=list(dict.fromkeys(r["player_id"] for r in rows)),
        gm_ids=names.gm_ids(*teams),
    )  # fmt: skip


def _scope_phrase(scope: str) -> str:
    """ "Atlantic League " for an award given in each league, else ""."""
    return f"{scope} " if scope.endswith("League") else ""


# ── Front offices and retirements ─────────────────────────────────────────────


def firings(conn, names: Names, league_id: str, season_id: str, on: str) -> None:
    news = NewsRepository(conn)
    for r in conn.execute(
        """SELECT e.gm_id, e.wins, e.losses, g.team_id, g.display_name
           FROM gm_season_evaluations e JOIN gms g ON g.id = e.gm_id
           WHERE e.season_id = %s AND e.verdict = 'fired' AND g.league_id = %s""",
        (season_id, league_id),
    ).fetchall():
        team = r["team_id"]
        news.add(
            league_id, season_id, on, "front_office", f"fired:{r['gm_id']}:{season_id}",
            f"{names.team(team)} fire {names.gm_name(names.gm(r['gm_id'])) or 'GM ' + r['display_name']}",
            f"After a {r['wins']}-{r['losses']} season, the {names.full_team(team)}"
            f" are looking for a new GM.",
            weight=3, team_ids=[team] if team else [], gm_ids=[r["gm_id"]],
        )  # fmt: skip


RETIREMENT_MARKS = (
    ("bat_home_runs", 200, "home runs"),
    ("bat_hits", 1500, "hits"),
    ("pitch_wins", 100, "wins"),
    ("pitch_strike_outs", 1500, "strikeouts"),
)


def retirements(conn, names: Names, league_id: str, season_id: str, on: str) -> None:
    news = NewsRepository(conn)
    rows = conn.execute(
        """SELECT r.player_id, r.former_team_id,
                  SUM(s.bat_home_runs) AS bat_home_runs, SUM(s.bat_hits) AS bat_hits,
                  SUM(s.pitch_wins) AS pitch_wins, SUM(s.pitch_strike_outs) AS pitch_strike_outs,
                  (SELECT COUNT(*) FROM all_stars a WHERE a.player_id = r.player_id) AS all_stars
           FROM player_retirements r
           LEFT JOIN player_season_stats s ON s.player_id = r.player_id AND NOT s.is_postseason
           WHERE r.league_id = %s AND r.season_id = %s
           GROUP BY r.player_id, r.former_team_id""",
        (league_id, season_id),
    ).fetchall()
    for r in rows:
        # (how far past the mark, total, label) for each mark reached
        best = [
            ((r[col] or 0) / mark, r[col], label)
            for col, mark, label in RETIREMENT_MARKS
            if (r[col] or 0) >= mark
        ]
        if not best and (r["all_stars"] or 0) < 3:
            continue
        pid, team = r["player_id"], r["former_team_id"]
        who = names.player(pid)
        if best:
            _, n, label = max(best)
            headline = f"{who} retires with {n:,} {label}"
        else:
            headline = f"{who} retires"
        body = f"{who} calls it a career"
        if team:
            body += f", last with the {names.full_team(team)}"
        body += "."
        if r["all_stars"]:
            body += (
                f" {r['all_stars']}-time All-Star."
                if r["all_stars"] > 1
                else " A one-time All-Star."
            )
        news.add(
            league_id, season_id, on, "retirement", f"retired:{pid}", headline, body,
            weight=2, team_ids=[team] if team else [], player_ids=[pid],
            gm_ids=names.gm_ids(team) if team else [],
        )  # fmt: skip


def hall_of_fame(conn, names: Names, league_id: str, season_id: str, year: int) -> None:
    """The Hall of Fame vote held as the season ended: a story for each
    player voted in, and one for the rest of the ballot (who came close,
    who fell off)."""
    news = NewsRepository(conn)
    rows = hof_service.for_season(conn, season_id)
    if not rows:
        return
    on = _now(conn, season_id)
    names.load_players(r["player_id"] for r in rows)
    for r in rows:
        if r["outcome"] != "elected":
            continue
        pid, team = r["player_id"], r["team_id"]
        who = names.player(pid)
        when = (
            "on his first ballot"
            if r["year_on_ballot"] == 1
            else f"in his {hof_service.ordinal(r['year_on_ballot'])} year on the ballot"
        )
        body = (
            f"{who} is a Hall of Famer, named on {r['votes']} of {r['ballots']}"
            f" ballots ({r['pct']}) {when}."
        )
        s = r["summary"]
        body += (
            f" {s.get('seasons')} seasons, {s.get('first_year')}–{s.get('last_year')}"
        )
        if team:
            body += f", his best years with the {names.full_team(team)}"
        body += f": {r['line']}."
        if r["honors"]:
            body += f" {r['honors']}."
        news.add(
            league_id, season_id, on, "hall_of_fame", f"hof:{pid}",
            f"{who} elected to the Hall of Fame", body,
            weight=3, team_ids=[team] if team else [], player_ids=[pid],
            gm_ids=names.gm_ids(team) if team else [],
        )  # fmt: skip

    story = f"hof:ballot:{season_id}"
    rest = [r for r in rows if r["outcome"] != "elected"]
    elected = [r for r in rows if r["outcome"] == "elected"]
    if news.has(league_id, story):
        return
    lines = []
    if not elected:
        lines.append(
            f"Nobody reached 75% in the {year} Hall of Fame vote"
            f" ({rows[0]['ballots']} ballots)."
        )
    close = [r for r in rest if r["share"] >= 0.5][:3]
    if close:
        lines.append(
            "Close: "
            + ", ".join(f"{names.player(r['player_id'])} {r['pct']}" for r in close)
            + "."
        )
    gone = [r for r in rest if r["outcome"] == "final" and r["share"] >= 0.2]
    for r in gone:
        lines.append(
            f"{names.player(r['player_id'])} runs out of time: {r['pct']} in his"
            " 10th and last year on the ballot."
        )
    first = [
        r
        for r in rest
        if r["year_on_ballot"] == 1 and r["share"] >= 0.3 and r not in close
    ]
    if first:
        lines.append(
            "Strong debuts: "
            + ", ".join(f"{names.player(r['player_id'])} {r['pct']}" for r in first[:3])
            + "."
        )
    if elected and not (close or gone or first):
        return  # the inductees' own stories cover it
    headline = (
        f"No one elected to the Hall of Fame in {year}"
        if not elected
        else f"The rest of the {year} Hall of Fame ballot"
    )
    shown = close + gone + first[:3]
    news.add(
        league_id, season_id, on, "hall_of_fame", story, headline, "\n".join(lines),
        weight=1, player_ids=list(dict.fromkeys(r["player_id"] for r in shown)),
        team_ids=list(dict.fromkeys(r["team_id"] for r in shown if r["team_id"])),
    )  # fmt: skip


def _now(conn, season_id: str) -> str:
    row = conn.execute(
        "SELECT MAX(game_date) AS d FROM games WHERE season_id = %s AND completed = 1",
        (season_id,),
    ).fetchone()
    if row and row["d"]:
        return row["d"]
    year = conn.execute(
        "SELECT year FROM seasons WHERE id = %s", (season_id,)
    ).fetchone()
    return f"{year['year'] if year else 2000}-03-22"
