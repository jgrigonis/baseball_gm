# src/api/services/hall_of_fame.py
"""
Hall of Fame elections (src/league/hall_of_fame.py) against the database.

decide_league() runs after every sim job, with the awards. Once a played
season's Finals are over (league_seasons.awards_done), it holds that year's
election, if the league has played enough seasons for anyone to be
eligible: players need 5 full seasons retired, and players who retired in
a backstory offseason never count, so the first election comes after the
league's 6th played season at the earliest. Missed elections (a league
that was already long when this was built) are held in order, oldest
first, since each year's holdovers come from the year before.

Reading: inductees(), ballots() and player_status() for the Hall of Fame
page, the season summary, the news and the player panel.
"""

from __future__ import annotations

import json
import logging
import random

from src.api.services import season_value
from src.league import hall_of_fame as hof
from src.name_generator.names import SimpleNameGenerator
from src.player.face import face_url

log = logging.getLogger(__name__)

ELECT_PCT = int(hof.ELECT_SHARE * 100)


# ── Careers ──────────────────────────────────────────────────────────────────


def load_careers(conn, league_id: str, player_ids: list[str]) -> dict[str, hof.Career]:
    """Each player's career in the league, as the writers see it."""
    if not player_ids:
        return {}
    rows = conn.execute(
        """SELECT pss.player_id, pss.season_id, pss.team_id, s.year, s.is_backstory,
                  pss.bat_games_played, pss.pitch_games_played,
                  pss.pitch_games_started, pss.bat_ab, pss.bat_hits,
                  pss.bat_home_runs, pss.pitch_wins, pss.pitch_strike_outs,
                  pss.pitch_saves, pss.pitch_outs, pss.pitch_earned_runs,
                  t.city, t.mascot
           FROM player_season_stats pss
           JOIN league_seasons ls ON ls.season_id = pss.season_id
           JOIN seasons s ON s.id = pss.season_id
           LEFT JOIN teams t ON t.id = pss.team_id
           WHERE ls.league_id = %s AND pss.player_id = ANY(%s)
             AND NOT pss.is_postseason
           ORDER BY s.year""",
        (league_id, player_ids),
    ).fetchall()
    champs = _champions(conn, league_id)
    # A season split between teams: his WAR goes to each by games played.
    season_games: dict[tuple[str, str], int] = {}
    for r in rows:
        key = (r["player_id"], r["season_id"])
        season_games[key] = season_games.get(key, 0) + _games(r)
    values: dict[str, dict] = {}
    careers = {pid: hof.Career(pid, []) for pid in player_ids}
    for r in rows:
        sid = r["season_id"]
        if sid not in values:
            values[sid] = season_value.season_values(conn, sid)
        v = values[sid].get(r["player_id"])
        hitter = r["bat_games_played"] >= r["pitch_games_played"]
        war = 0.0
        if v:
            total = season_games[(r["player_id"], sid)]
            war = v["WAR"] * (_games(r) / total if total else 1.0)
            hitter = v["hitter"]
        c = careers[r["player_id"]]
        c.seasons.append(
            hof.Season(
                year=r["year"],
                backstory=bool(r["is_backstory"]),
                war=war,
                hitter=hitter,
                games=_games(r),
                starts=r["pitch_games_started"],
                hits=r["bat_hits"],
                hr=r["bat_home_runs"],
                wins=r["pitch_wins"],
                k=r["pitch_strike_outs"],
                saves=r["pitch_saves"],
                ab=r["bat_ab"],
                outs=r["pitch_outs"],
                er=r["pitch_earned_runs"],
                team_id=r["team_id"],
                ring=champs.get(sid) == r["team_id"],
            )
        )
        if r["team_id"]:
            c.teams[r["team_id"]] = f"{r['city']} {r['mascot']}"
    honors = conn.execute(
        """SELECT a.player_id, a.award AS key, s.year, s.is_backstory
           FROM season_awards a
           JOIN league_seasons ls ON ls.season_id = a.season_id
           JOIN seasons s ON s.id = a.season_id
           WHERE ls.league_id = %(league)s AND a.player_id = ANY(%(ids)s)
           UNION ALL
           SELECT st.player_id, 'all_star', s.year, s.is_backstory
           FROM all_stars st
           JOIN league_seasons ls ON ls.season_id = st.season_id
           JOIN seasons s ON s.id = st.season_id
           WHERE ls.league_id = %(league)s AND st.player_id = ANY(%(ids)s)
             AND st.replaces IS NULL""",
        {"league": league_id, "ids": player_ids},
    ).fetchall()
    for h in honors:
        careers[h["player_id"]].honors.append(
            hof.Honor(h["key"], h["year"], bool(h["is_backstory"]))
        )
    return careers


def _games(r: dict) -> int:
    return max(r["bat_games_played"], r["pitch_games_played"])


def _champions(conn, league_id: str) -> dict[str, str]:
    """{season_id: champion team_id} for the league's finished seasons."""
    rows = conn.execute(
        """SELECT DISTINCT ON (sr.season_id) sr.season_id, g.winner_id, COUNT(*) AS w
           FROM series sr
           JOIN league_seasons ls ON ls.season_id = sr.season_id
           JOIN games g ON g.series_id = sr.id AND g.completed = 1
           WHERE ls.league_id = %s AND sr.name = 'Finals'
           GROUP BY sr.season_id, g.winner_id
           ORDER BY sr.season_id, w DESC""",
        (league_id,),
    ).fetchall()
    return {r["season_id"]: r["winner_id"] for r in rows if r["w"] >= 4}


# ── Elections ────────────────────────────────────────────────────────────────


def decide_league(conn, league_id: str) -> None:
    """Hold any election the league is due."""
    seasons = conn.execute(
        """SELECT s.id, s.year, s.is_backstory, ls.awards_done,
                  he.season_id IS NOT NULL AS held
           FROM league_seasons ls
           JOIN seasons s ON s.id = ls.season_id
           LEFT JOIN hall_elections he ON he.season_id = s.id
           WHERE ls.league_id = %s ORDER BY s.year""",
        (league_id,),
    ).fetchall()
    played = [s for s in seasons if not s["is_backstory"]]
    if not played:
        return
    first_year = played[0]["year"]
    for s in played:
        if s["held"] or not s["awards_done"]:
            continue
        if s["year"] - first_year < hof.WAIT_SEASONS:
            continue
        hold_election(conn, league_id, s["id"], s["year"], first_year)


def hold_election(
    conn, league_id: str, season_id: str, year: int, first_year: int
) -> list[hof.Result]:
    cands = _candidates(conn, league_id, year, first_year)
    voters = writers(conn, league_id)
    cast, results = hof.elect(cands, voters, random.Random(f"hof-{season_id}"))
    conn.execute(
        """INSERT INTO hall_elections (season_id, league_id, year, ballots)
           VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING""",
        (season_id, league_id, year, cast),
    )
    by_id = {c.career.player_id: c.career for c in cands}
    for r in results:
        career = by_id[r.player_id]
        conn.execute(
            """INSERT INTO hall_ballot (season_id, player_id, league_id, votes,
                   share, year_on_ballot, outcome, team_id, summary)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT DO NOTHING""",
            (
                season_id,
                r.player_id,
                league_id,
                r.votes,
                r.share,
                r.year_on_ballot,
                r.outcome,
                career.main_team(),
                json.dumps(summary(career)),
            ),
        )
    elected = [r for r in results if r.outcome == "elected"]
    log.info(
        "League %s: %s Hall of Fame election, %s on the ballot, %s elected",
        league_id,
        year,
        len(results),
        len(elected),
    )
    return results


def _candidates(
    conn, league_id: str, year: int, first_year: int
) -> list[hof.Candidate]:
    """This year's ballot: first-timers the screening committee lets on,
    and last year's holdovers."""
    retired = conn.execute(
        """SELECT pr.player_id, MAX(s.year) AS retired_year
           FROM player_retirements pr JOIN seasons s ON s.id = pr.season_id
           WHERE pr.league_id = %s AND NOT s.is_backstory AND s.year >= %s
           GROUP BY pr.player_id
           HAVING MAX(s.year) = %s""",
        (league_id, first_year, year - hof.WAIT_SEASONS),
    ).fetchall()
    last = conn.execute(
        """SELECT hb.player_id, hb.share, hb.year_on_ballot
           FROM hall_ballot hb JOIN hall_elections he ON he.season_id = hb.season_id
           WHERE hb.league_id = %s AND he.year = %s AND hb.outcome = 'returning'""",
        (league_id, year - 1),
    ).fetchall()
    on_ballot = {
        r["player_id"]
        for r in conn.execute(
            "SELECT DISTINCT player_id FROM hall_ballot WHERE league_id = %s",
            (league_id,),
        ).fetchall()
    }
    new_ids = [r["player_id"] for r in retired if r["player_id"] not in on_ballot]
    careers = load_careers(conn, league_id, new_ids + [r["player_id"] for r in last])
    out = []
    for r in retired:
        c = careers.get(r["player_id"])
        if (
            c
            and r["player_id"] not in on_ballot
            and hof.eligible(c, r["retired_year"], year)
            and hof.passes_screening(c)
        ):
            out.append(hof.Candidate(c, 1))
    for r in last:
        out.append(
            hof.Candidate(careers[r["player_id"]], r["year_on_ballot"] + 1, r["share"])
        )
    return out


def writers(conn, league_id: str) -> list[hof.Writer]:
    teams = conn.execute(
        """SELECT DISTINCT t.id, t.city FROM league_season_teams lst
           JOIN teams t ON t.id = lst.team_id WHERE lst.league_id = %s""",
        (league_id,),
    ).fetchall()
    names = SimpleNameGenerator()

    def make_name(rng: random.Random) -> str:
        names.rng = rng
        first, last = names.full("male")
        return f"{first} {last}"

    return hof.writers(league_id, [(t["id"], t["city"]) for t in teams], make_name)


def summary(c: hof.Career) -> dict:
    """The career numbers kept with a ballot row, for the pages."""
    out = {
        "hitter": c.hitter,
        "reliever": c.reliever,
        "seasons": c.num_seasons,
        "backstory_seasons": len({s.year for s in c.seasons if s.backstory}),
        "first_year": c.first_year,
        "last_year": c.last_year,
        "war": round(c.raw_war, 1),
        "weighted_war": round(c.war, 1),
        "jaws": round(c.jaws, 1),
        "all_stars": int(c.honors_count("all_star", weighted=False)),
        "rings": c.raw_rings,
        "awards": {},
    }
    for h in c.honors:
        if h.key != "all_star":
            out["awards"][h.key] = out["awards"].get(h.key, 0) + 1
    if c.hitter:
        ab = c.raw_total("ab")
        out.update(
            hits=c.raw_total("hits"),
            hr=c.raw_total("hr"),
            avg=round(c.raw_total("hits") / ab, 3) if ab else 0.0,
        )
    else:
        outs = c.raw_total("outs")
        out.update(
            wins=c.raw_total("wins"),
            k=c.raw_total("k"),
            saves=c.raw_total("saves"),
            era=round(27 * c.raw_total("er") / outs, 2) if outs else 0.0,
        )
    return out


# ── Reading ──────────────────────────────────────────────────────────────────


def has_hall(conn, league_id: str) -> bool:
    """Whether the league has held an election yet (the page shows then)."""
    return (
        conn.execute(
            "SELECT 1 FROM hall_elections WHERE league_id = %s LIMIT 1", (league_id,)
        ).fetchone()
        is not None
    )


PLAQUE_AGE = 34

_ROW_SQL = """SELECT hb.*, he.year, he.ballots, p.first_name, p.last_name,
                     p.position, t.city, t.mascot
              FROM hall_ballot hb
              JOIN hall_elections he ON he.season_id = hb.season_id
              JOIN players p ON p.id = hb.player_id
              LEFT JOIN teams t ON t.id = hb.team_id"""


def _row(r: dict, my_team_id: str | None = None) -> dict:
    s = r["summary"] or {}
    return {
        "player_id": r["player_id"],
        "name": f"{r['first_name']} {r['last_name']}",
        "position": (r["position"] or "").upper(),
        "team": f"{r['city']} {r['mascot']}" if r["city"] else "",
        "team_id": r["team_id"],
        "is_mine": bool(my_team_id and r["team_id"] == my_team_id),
        "year": r["year"],
        "votes": r["votes"],
        "ballots": r["ballots"],
        "share": r["share"],
        "pct": f"{100 * r['share']:.1f}%",
        "year_on_ballot": r["year_on_ballot"],
        "outcome": r["outcome"],
        "summary": s,
        "line": career_line(s),
        "honors": honors_line(s),
        # On his plaque he wears the cap of the team he gave the most to.
        "face": face_url(r["player_id"], PLAQUE_AGE, r["city"], r["mascot"]),
    }


def career_line(s: dict) -> str:
    """A career in a few numbers: 2,412 H · 388 HR · .281 · 61.2 WAR."""
    if not s:
        return ""
    if s.get("hitter"):
        parts = [
            f"{s.get('hits', 0):,} H",
            f"{s.get('hr', 0):,} HR",
            f"{s.get('avg', 0):.3f}".lstrip("0") + " AVG",
        ]
    elif s.get("reliever"):
        parts = [
            f"{s.get('saves', 0):,} SV",
            f"{s.get('era', 0):.2f} ERA",
            f"{s.get('k', 0):,} K",
        ]
    else:
        parts = [
            f"{s.get('wins', 0):,} W",
            f"{s.get('era', 0):.2f} ERA",
            f"{s.get('k', 0):,} K",
        ]
    parts.append(f"{s.get('war', 0):.1f} WAR")
    return " · ".join(parts)


_HONOR_NAMES = (
    ("mvp", "MVP", "MVPs"),
    ("cy_young", "Cy Young", "Cy Youngs"),
    ("reliever", "Reliever of the Year", "Reliever of the Year ×{n}"),
    ("finals_mvp", "Finals MVP", "Finals MVP ×{n}"),
    ("gold_glove", "Gold Glove", "Gold Gloves"),
    ("silver_slugger", "Silver Slugger", "Silver Sluggers"),
)


def honors_line(s: dict) -> str:
    """His best honors: 2 MVPs · 9 All-Star picks · 1 ring."""
    if not s:
        return ""
    awards = s.get("awards") or {}
    parts = []
    for key, one, many in _HONOR_NAMES:
        n = awards.get(key, 0)
        if n == 1:
            parts.append(one)
        elif n > 1:
            parts.append(many.format(n=n) if "{n}" in many else f"{n} {many}")
    stars = s.get("all_stars", 0)
    if stars:
        parts.append(f"{stars}× All-Star")
    rings = s.get("rings", 0)
    if rings:
        parts.append(f"{rings} ring{'s' if rings > 1 else ''}")
    return " · ".join(parts)


def inductees(conn, league_id: str, my_team_id: str | None = None) -> list[dict]:
    """Every Hall of Famer, newest class first."""
    rows = conn.execute(
        _ROW_SQL
        + """ WHERE hb.league_id = %s AND hb.outcome = 'elected'
                       ORDER BY he.year DESC, hb.share DESC""",
        (league_id,),
    ).fetchall()
    return [_row(r, my_team_id) for r in rows]


def election_years(conn, league_id: str) -> list[int]:
    rows = conn.execute(
        "SELECT year FROM hall_elections WHERE league_id = %s ORDER BY year DESC",
        (league_id,),
    ).fetchall()
    return [r["year"] for r in rows]


def ballot(
    conn, league_id: str, year: int, my_team_id: str | None = None
) -> list[dict]:
    """One year's ballot results, most votes first."""
    rows = conn.execute(
        _ROW_SQL
        + """ WHERE hb.league_id = %s AND he.year = %s
                       ORDER BY hb.votes DESC, p.last_name""",
        (league_id, year),
    ).fetchall()
    return [_row(r, my_team_id) for r in rows]


def for_season(conn, season_id: str, my_team_id: str | None = None) -> list[dict]:
    """The election held after a season, most votes first (empty if none)."""
    rows = conn.execute(
        _ROW_SQL + """ WHERE hb.season_id = %s ORDER BY hb.votes DESC, p.last_name""",
        (season_id,),
    ).fetchall()
    return [_row(r, my_team_id) for r in rows]


def player_status(conn, player_id: str) -> dict | None:
    """His Hall of Fame standing: elected (with the year and share), or his
    latest ballot, or None if he's never been on one."""
    r = conn.execute(
        _ROW_SQL
        + """ WHERE hb.player_id = %s
                       ORDER BY (hb.outcome = 'elected') DESC, he.year DESC
                       LIMIT 1""",
        (player_id,),
    ).fetchone()
    return _row(r) if r else None


def ordinal(n: int) -> str:
    """1st, 2nd, 3rd, 4th, ... 11th, 12th, 13th."""
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def badge(conn, player_id: str) -> dict | None:
    """The player panel's and career page's Hall of Fame badge: {text,
    title, elected}, or None if he's never been on a ballot."""
    st = player_status(conn, player_id)
    if not st:
        return None
    yr = f"{ordinal(st['year_on_ballot'])} year on the ballot"
    if st["outcome"] == "elected":
        return {
            "text": f"Hall of Fame {st['year']}",
            "title": f"Elected in {st['year']} with {st['pct']} of the vote, {yr}"
            if st["year_on_ballot"] > 1
            else f"Elected in {st['year']} with {st['pct']} of the vote, on the first ballot",
            "elected": True,
        }
    if st["outcome"] == "returning":
        return {
            "text": f"HOF ballot · {st['pct']}",
            "title": f"{st['year']} Hall of Fame vote: {st['pct']} ({ELECT_PCT}% gets in), {yr}",
            "elected": False,
        }
    why = "his 10th and last year" if st["outcome"] == "final" else "under 5%"
    return {
        "text": "Off the HOF ballot",
        "title": f"{st['year']} Hall of Fame vote: {st['pct']}, {why}, so he's off the ballot",
        "elected": False,
    }
