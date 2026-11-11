# src/api/services/owner_office.py
#
# The owner's office: what each owner says to their GM, and how they feel
# (src/league/owner_messages.py). Messages are stored once, under a key, so
# writing them is safe to repeat:
#
#   pre:<season>            the preseason memo: what they want, and the budget
#   check:<season>:<n>      check-ins through the season, more if chatty
#   trade:<offer>           a reaction to a trade, if it touches what they care about
#   release:<deal>,<deal>   a reaction to releasing players (one message for
#                           every release since they last looked), by deal id
#   streak:<start>:<n>      a reaction to a winning or losing streak in the news
#   veto:<player>:<year>    a meddler refusing to let the GM release him
#   over:<season>           payroll went over budget
#   review:<season>         the end-of-season review and how safe the job is
#
# catch_up() writes whatever is due; the sim calls it once a week and the
# Owner tab when it opens. reactions() (moves and streaks) is cheaper and runs
# every sim day, and right after a release. review() runs when the playoffs end, after the
# season review (owner_review.py). Mood is updated weekly in season, from the
# same scoring the review uses, on the season so far.

from __future__ import annotations

import random
from dataclasses import replace
from datetime import date

from src.api.grade_curves import GRADES
from src.api.services import icons, owner_review
from src.api.services.news.moves import is_notable
from src.api.services import owners as owner_service
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.contract_repo import ContractRepository
from src.db.repositories.owner_repo import OwnerRepository
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


def _wrote_to(conn, league_id: str, team_id: str, gm_id: str) -> bool:
    """Whether the team's owner has written to this GM before."""
    return bool(
        conn.execute(
            """SELECT 1 FROM owner_messages
               WHERE league_id = %s AND team_id = %s AND gm_id = %s LIMIT 1""",
            (league_id, team_id, gm_id),
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


def _checkins(conn, league_id: str, team_id: str, season_id: str) -> list[str]:
    """The team's owner's check-ins this season, newest first."""
    rows = conn.execute(
        """SELECT body FROM owner_messages
           WHERE league_id = %s AND team_id = %s AND season_id = %s
             AND kind = 'checkin'
           ORDER BY id DESC""",
        (league_id, team_id, season_id),
    ).fetchall()
    return [r["body"] for r in rows]


def moods(conn, league_id: str, season_id: str) -> dict[str, dict]:
    rows = conn.execute(
        """SELECT team_id, mood, as_of FROM owner_moods
           WHERE league_id = %s AND season_id = %s""",
        (league_id, season_id),
    ).fetchall()
    return {r["team_id"]: dict(r) for r in rows}


def latest_moods(
    conn, league_id: str, before_year: int | None = None
) -> dict[str, float]:
    """Each team's owner's newest mood from any season in this league (before
    before_year if given). A new season has no mood row until its first week
    of games, so this carries last season's mood (the review) until then."""
    rows = conn.execute(
        """SELECT DISTINCT ON (m.team_id) m.team_id, m.mood
           FROM owner_moods m JOIN seasons s ON s.id = m.season_id
           WHERE m.league_id = %s AND (%s::int IS NULL OR s.year < %s::int)
           ORDER BY m.team_id, s.year DESC""",
        (league_id, before_year, before_year),
    ).fetchall()
    return {r["team_id"]: r["mood"] for r in rows}


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
    leagues cost: the money they're giving the GM for payroll, after the
    luxury tax a payroll over the cap owes (src/league/budget.py)."""
    repo = BudgetRepository(conn)
    budgets = repo.for_league(league_id, year)
    if not budgets:
        return {}
    cap = repo.cap(league_id, year)
    levels = repo.league_levels(league_id, year)
    farms = repo.league_minor_leagues(league_id, year)
    return {
        t: bg.payroll_within(
            b - bg.front_office_cost(cap, levels.get(t, {})) - farms.get(t, 0), cap
        )
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


def _in_season(season, traits: dict, money: bool, state: str) -> dict:
    """The owner's scores on the season so far. Until the playoffs start,
    nobody has made or missed them, so the postseason isn't judged yet
    (score_dimensions would read every team as having missed)."""
    scores = sc.score_dimensions(season, traits, money)
    if state == "season":
        scores["postseason"] = None
    return scores


def weekly(conn, league_id: str, today: str) -> int:
    """From the sim, after a day's games: catch up once a week (the first
    day of the season, then every MOOD_DAYS), and react to moves and streaks
    every day."""
    season = _season(conn, league_id)
    if not season:
        return 0
    row = conn.execute(
        """SELECT MIN(as_of) AS as_of FROM owner_moods
           WHERE league_id = %s AND season_id = %s""",
        (league_id, season["id"]),
    ).fetchone()
    judging = conn.execute(
        "SELECT 1 FROM team_owners WHERE league_id = %s AND since_year <= %s LIMIT 1",
        (league_id, season["year"]),
    ).fetchone()
    if not judging:  # owners who arrived mid-season wait for next season
        return 0
    if row and row["as_of"] and _days(row["as_of"], today) < MOOD_DAYS:
        return reactions(conn, league_id, today)
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
    # The first reading of a season starts from where last season left off.
    before = latest_moods(conn, league_id, year) if in_season else {}
    contracts = ContractRepository(conn)
    # The books don't close until the season ends, so in season owners judge
    # the money on the Budget tab's projection: today's payroll for the year.
    projected = (
        BudgetRepository(conn).projected(league_id, year) if money and in_season else {}
    )
    for team_id, owner in by_team.items():
        gm = gms.get(team_id)
        if not gm or year < owner["since_year"]:
            continue
        fields = _fields(owner, gm, names, budgets.get(team_id))
        sid = season["id"]
        # The preseason memo, before or early in the season.
        if not _has(conn, league_id, team_id, f"pre:{sid}"):
            first = not _wrote_to(conn, league_id, team_id, gm["id"])
            body = om.preseason(
                owner["weights"], fields, _rng(sid, team_id, "pre"), money, first
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
        payroll = contracts.payroll(team_id, year)
        so_far = replace(facts[team_id], payroll=payroll)
        p = projected.get(team_id)
        if p and so_far.profit is None:
            so_far = replace(so_far, revenue=p["revenue"], profit=p["profit"])
        said = om.facts(so_far.as_dict(), payroll, budgets.get(team_id))
        if today and (m is None or _days(m["as_of"], today) >= MOOD_DAYS):
            scores = _in_season(so_far, owner["traits"], money, league["state"])
            reading = sc.season_score(scores, owner["weights"])
            reading *= min(1.0, games / MOOD_FULL_GAMES)
            start = m["mood"] if m else before.get(team_id, 0.0)
            mood = om.next_mood(start, reading, traits["temper"])
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
                scores = _in_season(so_far, owner["traits"], money, league["state"])
                mood = current.get(team_id, {}).get("mood", 0.0)
                body = om.checkin(
                    scores, owner["weights"], fields, _rng(sid, team_id, n), money,
                    _recent(conn, league_id, team_id), mood, said,
                    _checkins(conn, league_id, team_id, sid),
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
            and payroll > budget
            and not _has(conn, league_id, team_id, f"over:{sid}")
        ):
            body = om.over_budget(
                {**fields, "payroll": format_salary(payroll)},
                _rng(sid, team_id, "over"),
            )
            written += _write(
                conn, league_id, team_id, gm["id"], sid, f"over:{sid}", "budget",
                body, today, None,
            )  # fmt: skip
    return written + reactions(conn, league_id, today)


def reactions(conn, league_id: str, today: str | None = None, team_ids=None) -> int:
    """Each owner's word on what's happened since they last looked: trades,
    releases, and streaks in the news. Only for teams in team_ids, if given.
    Returns how many messages were written."""
    league = _league(conn, league_id)
    season = _season(conn, league_id)
    if not league or not season or league["state"] in ("lobby", "complete"):
        return 0
    by_team = OwnerRepository(conn).in_league(league_id)  # seated by catch_up
    if team_ids is not None:
        by_team = {t: o for t, o in by_team.items() if t in set(team_ids)}
    gms = _gms(conn, league_id)
    names = _team_names(conn, by_team) if by_team else {}
    written = 0
    for team_id, owner in by_team.items():
        gm = gms.get(team_id)
        if not gm or season["year"] < owner["since_year"]:
            continue
        fields = _fields(owner, gm, names, None)
        written += _trade_reactions(
            conn, league_id, season["id"], team_id, gm, owner, fields, today
        )
        if gm["is_ai"]:  # nobody reads them
            continue
        written += _release_reactions(
            conn, league_id, season, team_id, gm, owner, fields, today
        )
        written += _streak_reactions(
            conn, league_id, season["id"], team_id, gm, owner, fields, today
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
                  ARRAY(SELECT i.player_id FROM trade_offer_items i
                        WHERE i.offer_id = o.id AND i.from_team_id = %s) AS sent,
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
        icon_out = w["icons"] >= owners.STRONG and icons.find(
            conn, [(pid, team_id) for pid in t["sent"] or []]
        )
        if icon_out:
            what = "icons"
        elif t["star_in"] and w["stars"] >= owners.STRONG:
            what = "stars"
        elif w["stability"] >= owners.STRONG:
            what = "stability"
        elif owners.clean_traits(owner["traits"])["meddling"] >= om.MEDDLES:
            what = "meddling"
        if what:
            body = om.trade_reaction(what, fields, _rng(t["id"], team_id))
            written += _write(
                conn, league_id, team_id, gm["id"], season_id, key, "trade", body,
                today, None,
            )  # fmt: skip
    return written


# Guaranteed money still owed that makes a release worth a word on its own,
# whatever the player's grade.
DEAD_MONEY_FLOOR = 2_000_000
# How far one reaction moves the owner's mood, before temper (-1 to 1 scale).
# The weekly reading then pulls it back toward how the season reads.
RELEASE_MOOD = {
    "icons": -0.25,
    "meddling_money": -0.2,
    "meddling": -0.15,
    "dead_money": -0.1,
    "stars": -0.1,
    "stability": -0.05,
}


def _reacted_releases(conn, league_id: str, team_id: str) -> set[int]:
    rows = conn.execute(
        """SELECT key FROM owner_messages
           WHERE league_id = %s AND team_id = %s AND key LIKE 'release:%%'""",
        (league_id, team_id),
    ).fetchall()
    out: set[int] = set()
    for r in rows:
        for part in r["key"].split(":", 1)[1].split(","):
            if part.isdigit():
                out.add(int(part))
    return out


def _names_list(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def release_reason(
    owner: dict, icon: bool, notable: bool, star: bool, owed: int
) -> str | None:
    """What, if anything, bothers this owner about a batch of releases:
    a RELEASE_REACTIONS key. notable: one was B- or better; star: one was an
    A; owed: the guaranteed money still owed them all."""
    w = owners.clean_weights(owner["weights"])
    meddles = owners.clean_traits(owner["traits"])["meddling"] >= om.MEDDLES
    big_money = owed >= DEAD_MONEY_FLOOR
    if icon and (w["icons"] >= owners.STRONG or meddles):
        return "icons"
    if meddles and (notable or big_money):
        return "meddling_money" if big_money else "meddling"
    if big_money and w["profit"] >= owners.STRONG:
        return "dead_money"
    if star and w["stars"] >= owners.STRONG:
        return "stars"
    if notable and w["stability"] >= owners.STRONG:
        return "stability"
    return None


def _release_reactions(
    conn, league_id, season, team_id, gm, owner, fields, today
) -> int:
    """One word on the players the team released this season since the owner
    last looked, if one was good (B- or better), an icon, or leaves real
    dead money, and that touches what the owner cares about. A meddler
    always has something to say."""
    done = _reacted_releases(conn, league_id, team_id)
    rows = [
        dict(r)
        for r in conn.execute(
            """SELECT c.id, c.player_id, c.salary, c.guaranteed,
                      c.start_year + c.years - c.released_year AS seasons,
                      p.first_name, p.last_name
               FROM player_contracts c JOIN players p ON p.id = c.player_id
               WHERE c.league_id = %s AND c.released_team_id = %s
                 AND c.released_year = %s
               ORDER BY c.id""",
            (league_id, team_id, season["year"]),
        ).fetchall()
        if r["id"] not in done
    ]
    if not rows:
        return 0
    grades = icons._grades(conn, list({r["player_id"] for r in rows}))
    found = icons.find(conn, [(r["player_id"], team_id) for r in rows], grades)
    picked = []
    for r in rows:
        g = grades.get(r["player_id"], "?")
        r["notable"] = g in GRADES and is_notable(g)
        r["star"] = g.startswith("A")
        r["icon"] = (r["player_id"], team_id) in found
        r["owed"] = r["salary"] * max(0, r["seasons"]) if r["guaranteed"] else 0
        if r["notable"] or r["icon"] or r["owed"] >= DEAD_MONEY_FLOOR:
            picked.append(r)
    if not picked:
        return 0
    owed = sum(r["owed"] for r in picked)
    what = release_reason(
        owner,
        any(r["icon"] for r in picked),
        any(r["notable"] for r in picked),
        any(r["star"] for r in picked),
        owed,
    )
    if not what:
        return 0
    # The players the owner names: the ones that bother them, worst first.
    if what == "icons":
        picked.sort(key=lambda r: not r["icon"])
    elif what in ("meddling_money", "dead_money"):
        picked.sort(key=lambda r: -r["owed"])
    who = [f"{r['first_name']} {r['last_name']}" for r in picked]
    body = om.release_reaction(
        what,
        {
            **fields,
            "player": who[0],
            "players": _names_list(who),
            "owed": format_salary(owed),
        },
        len(who) > 1,
        _rng(season["id"], team_id, *[r["id"] for r in picked]),
    )
    key = "release:" + ",".join(str(r["id"]) for r in picked)
    wrote = _write(
        conn, league_id, team_id, gm["id"], season["id"], key, "release", body,
        today, None,
    )  # fmt: skip
    if wrote:
        _nudge_mood(conn, league_id, team_id, season["id"], owner, RELEASE_MOOD[what])
    return int(wrote)


def release_veto(
    conn, league_id: str, team_id: str, player_id: str, announce: bool = False
) -> str | None:
    """A meddling owner's refusal to let a person's team release a player
    who is B- or better or a franchise icon, in their words; None when the
    release can go ahead. announce: also keep it in the owner's office
    (once per player a season). AI GMs only release their worst players and
    are never stopped."""
    season = _season(conn, league_id)
    league = _league(conn, league_id)
    if not season or not league or league["state"] in ("lobby", "complete"):
        return None
    owner = OwnerRepository(conn).in_league(league_id).get(team_id)
    gm = _gms(conn, league_id).get(team_id)
    if not owner or not gm or gm["is_ai"] or season["year"] < owner["since_year"]:
        return None
    if owners.clean_traits(owner["traits"])["meddling"] < om.MEDDLES:
        return None
    grade = icons._grades(conn, [player_id]).get(player_id, "?")
    icon = bool(icons.find(conn, [(player_id, team_id)], {player_id: grade}))
    if not icon and not (grade in GRADES and is_notable(grade)):
        return None
    row = conn.execute(
        "SELECT first_name, last_name FROM players WHERE id = %s", (player_id,)
    ).fetchone()
    fields = {
        **_fields(owner, gm, _team_names(conn, [team_id]), None),
        "player": f"{row['first_name']} {row['last_name']}" if row else "him",
    }
    key = f"veto:{player_id}:{season['year']}"
    said = conn.execute(
        """SELECT body FROM owner_messages
           WHERE league_id = %s AND team_id = %s AND key = %s""",
        (league_id, team_id, key),
    ).fetchone()
    if said:
        return said["body"]
    body = om.release_veto(icon, fields, _rng(key, team_id))
    if announce:
        from src.api.services.news.moves import today as league_today

        _write(
            conn, league_id, team_id, gm["id"], season["id"], key, "veto", body,
            league_today(conn, season["id"]), None,
        )  # fmt: skip
    return body


# Streak lengths an owner reacts to: every losing streak the news runs, and
# the long winning ones.
WIN_STREAK_FLOOR = 10


def _streak_reactions(
    conn, league_id, season_id, team_id, gm, owner, fields, today
) -> int:
    """A word on this GM's latest streak in the news, from owners who care
    about winning, have a temper, or meddle."""
    w = owners.clean_weights(owner["weights"])
    t = owners.clean_traits(owner["traits"])
    if not (
        t["meddling"] >= om.MEDDLES
        or t["temper"] >= owners.STRONG
        or w["wins"] >= owners.STRONG
    ):
        return 0
    rows = conn.execute(
        """SELECT key, headline FROM league_news
           WHERE league_id = %s AND season_id = %s AND kind = 'streak'
             AND %s = ANY(team_ids) AND %s = ANY(gm_ids)""",
        (league_id, season_id, team_id, gm["id"]),
    ).fetchall()
    # The longest mark of each streak, by its first day.
    longest: dict[str, tuple[int, bool]] = {}
    for r in rows:
        parts = r["key"].split(":")
        if len(parts) != 4 or not parts[3].isdigit():
            continue
        start, n = parts[2], int(parts[3])
        won = " drop " not in r["headline"]
        if n > longest.get(start, (0, won))[0]:
            longest[start] = (n, won)
    written = 0
    for start, (n, won) in sorted(longest.items()):
        if won and n < WIN_STREAK_FLOOR:
            continue
        key = f"streak:{start}:{n}"
        if _has(conn, league_id, team_id, key):
            continue
        body = om.streak_reaction(won, n, fields, _rng(season_id, team_id, key))
        if _write(
            conn, league_id, team_id, gm["id"], season_id, key, "streak", body,
            today, None,
        ):  # fmt: skip
            written += 1
            delta = 0.1 if won else -0.05 * n / 4
            _nudge_mood(conn, league_id, team_id, season_id, owner, delta)
    return written


def _nudge_mood(conn, league_id, team_id, season_id, owner, delta: float) -> None:
    """Move this season's mood by delta right away, more for a hot temper.
    Until the season's first weekly reading there's no mood to move."""
    temper = owners.clean_traits(owner["traits"])["temper"]
    conn.execute(
        """UPDATE owner_moods
           SET mood = GREATEST(-1, LEAST(1, mood + %s))
           WHERE league_id = %s AND team_id = %s AND season_id = %s""",
        (round(delta * (0.5 + temper / 100), 4), league_id, team_id, season_id),
    )


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
        """SELECT g.team_id, e.gm_id, e.score, e.job_security, e.detail, e.verdict
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
            "fired"
            if r["verdict"] == "fired"
            else "warned"
            if security < sc.HOT_SEAT
            else "fine"
            if security < 60
            else "safe"
        )
        fields = _fields(owner, gm, names, None)
        scores = (r["detail"] or {}).get("scores", {})
        said = om.facts((r["detail"] or {}).get("facts"), final=True)
        body = om.review(
            scores,
            owner["weights"],
            fields,
            band,
            _rng(season_id, r["team_id"], "rv"),
            money,
            said,
        )
        _set_mood(conn, league_id, r["team_id"], season_id, r["score"], today)
        written += _write(
            conn, league_id, r["team_id"], r["gm_id"], season_id, f"review:{season_id}",
            "review", body, today, om.mood_word(r["score"]),
        )  # fmt: skip
    return written


def office(conn, league_id: str, team_id: str, gm_id: str) -> dict:
    """What the GM sees in the owner's office: the mood word and their
    messages, newest first. Marks them seen. Between seasons and before the
    first week's games, the mood is last season's; an owner with no mood yet
    is content (a mood of 0)."""
    season = _season(conn, league_id)
    m = moods(conn, league_id, season["id"]).get(team_id) if season else None
    if m:
        mood = om.mood_word(m["mood"])
    else:
        mood = om.mood_word(latest_moods(conn, league_id).get(team_id, 0.0))
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
    messages, older = _split_recent([dict(r) for r in rows])
    return {"mood": mood, "messages": messages, "older": older}


def _split_recent(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Recent messages up front, the rest behind an "Older messages" button:
    everything from the newest season, plus last season's review until this
    season has its own. Unread messages always stay up front. Newest first."""
    if not rows:
        return [], []
    year = rows[0]["year"]
    has_review = any(r["year"] == year and r["kind"] == "review" for r in rows)
    last_review = None
    if not has_review:
        last_review = next(
            (r["id"] for r in rows if r["kind"] == "review" and r["year"] < year), None
        )
    recent, older = [], []
    for r in rows:
        keep = r["year"] == year or r["id"] == last_review or not r["seen_at"]
        (recent if keep else older).append(r)
    return recent, older


def preseason_memo(conn, league_id: str, team_id: str, gm_id: str, season_id: str):
    """This season's preseason memo to the GM, writing it first if it's due,
    with the owner's mood. None if there isn't one (no owner yet, or they
    don't judge this season)."""
    catch_up(conn, league_id)
    row = conn.execute(
        """SELECT body FROM owner_messages
           WHERE league_id = %s AND team_id = %s AND gm_id = %s AND key = %s""",
        (league_id, team_id, gm_id, f"pre:{season_id}"),
    ).fetchone()
    if not row:
        return None
    m = moods(conn, league_id, season_id).get(team_id)
    mood = m["mood"] if m else latest_moods(conn, league_id).get(team_id, 0.0)
    return {"body": row["body"], "mood": om.mood_word(mood)}


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
