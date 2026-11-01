# src/api/services/awards.py
"""
Season awards (src/league/awards.py) against the database.

decide_league() runs after every sim job (sim_jobs._record_careers) and
catches up: once a season's regular season is over it decides that
season's awards, and as each Semifinals and Finals series is won it names
the series MVP. Each season is marked in league_seasons (awards_regular,
awards_done), so a season is only looked at until everything it will have
is decided. Seasons played before awards existed, backstory ones included,
get theirs the same way the next time the league sims; GM of the Year only
for the season being played, since who ran each team back then isn't kept.
"""

from __future__ import annotations

from src.league import awards, divisions

_COLUMNS = (
    "bat_games_played",
    "bat_games_started",
    "bat_ab",
    "bat_hits",
    "bat_doubles",
    "bat_triples",
    "bat_home_runs",
    "bat_rbi",
    "bat_runs",
    "bat_walks",
    "bat_hbp",
    "bat_sac_flys",
    "bat_stolen_bases",
    "bat_caught_stealing",
    "pitch_games_played",
    "pitch_games_started",
    "pitch_wins",
    "pitch_losses",
    "pitch_saves",
    "pitch_holds",
    "pitch_outs",
    "pitch_hits",
    "pitch_earned_runs",
    "pitch_home_runs",
    "pitch_walks",
    "pitch_hit_batters",
    "pitch_strike_outs",
)

# Series names by round (src/api/services/career.py ROUND_OF_SERIES).
SEMIS = ("[1,8]v[4,5]", "[2,7]v[3,6]")
FINALS = "Finals"
WINS_NEEDED = 4


def decide_league(conn, league_id: str) -> None:
    rows = conn.execute(
        """SELECT s.id, s.year, s.is_backstory, ls.awards_regular, ls.awards_done
           FROM league_seasons ls JOIN seasons s ON s.id = ls.season_id
           WHERE ls.league_id = %s ORDER BY s.year""",
        (league_id,),
    ).fetchall()
    if not rows:
        return
    scope_of = _scopes(conn, league_id)
    latest = rows[-1]["id"]
    for i, s in enumerate(rows):
        if s["awards_done"]:
            continue
        sid = s["id"]
        dates = _dates(conn, sid)
        if not dates["regular_over"]:
            continue
        if not s["awards_regular"]:
            _decide_regular(
                conn,
                league_id,
                s,
                scope_of,
                first_season=i == 0,
                with_gm=sid == latest and not s["is_backstory"],
                on=dates["last_regular"],
            )
            _mark(conn, league_id, sid, "awards_regular")
        finals_done = _decide_series(conn, sid, scope_of)
        if s["is_backstory"] or finals_done or sid != latest:
            _mark(conn, league_id, sid, "awards_done")


def _mark(conn, league_id: str, season_id: str, column: str) -> None:
    conn.execute(
        f"UPDATE league_seasons SET {column} = TRUE"
        " WHERE league_id = %s AND season_id = %s",
        (league_id, season_id),
    )


def _scopes(conn, league_id: str) -> dict[str, str]:
    """Each team's league (Atlantic or Pacific); empty without divisions."""
    return {
        t: conf.name for conf in divisions.load(conn, league_id) for t in conf.team_ids
    }


def _dates(conn, season_id: str) -> dict:
    row = conn.execute(
        """SELECT MAX(game_date) FILTER (WHERE completed = 1 AND series_id IS NULL)
                      AS last_regular,
                  COUNT(*) FILTER (WHERE series_id IS NULL) AS regular,
                  COUNT(*) FILTER (WHERE series_id IS NULL
                                   AND (completed = 0 OR completed IS NULL)) AS left_to_play
           FROM games WHERE season_id = %s""",
        (season_id,),
    ).fetchone()
    return {
        "last_regular": row["last_regular"],
        "regular_over": row["regular"] > 0 and row["left_to_play"] == 0,
    }


def _save(conn, season_id: str, row: dict, on: str | None) -> None:
    conn.execute(
        """INSERT INTO season_awards (season_id, award, scope, player_id, team_id,
               gm_id, line, value, decided_on)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (season_id, award, scope) DO NOTHING""",
        (
            season_id, row["award"], row["scope"], row.get("player_id"),
            row.get("team_id"), row.get("gm_id"), row["line"], row.get("value"), on,
        ),
    )  # fmt: skip


# ── The regular season ────────────────────────────────────────────────────────


def _records(conn, season_id: str) -> dict[str, tuple[int, int]]:
    return {
        r["team_id"]: (int(r["wins"] or 0), int(r["losses"] or 0))
        for r in conn.execute(
            """SELECT tgs.team_id, SUM(tgs.win) AS wins, SUM(tgs.loss) AS losses
               FROM team_game_stats tgs JOIN games g ON g.id = tgs.game_id
               WHERE g.season_id = %s AND g.series_id IS NULL AND g.completed = 1
               GROUP BY tgs.team_id""",
            (season_id,),
        ).fetchall()
    }


def candidates(conn, season_id: str, year: int, scope_of: dict[str, str]) -> list[dict]:
    """Everyone who played in the regular season, with his totals and what
    src/league/awards.regular_awards() needs to know about him."""
    sums = ", ".join(f"SUM(pss.{c}) AS {c}" for c in _COLUMNS)
    rows = conn.execute(
        f"""WITH tot AS (
                SELECT pss.player_id, {sums},
                       (ARRAY_AGG(pss.team_id ORDER BY
                            pss.bat_games_played + pss.pitch_games_played DESC,
                            pss.team_id))[1] AS team_id
                FROM player_season_stats pss
                WHERE pss.season_id = %(season)s AND NOT pss.is_postseason
                GROUP BY pss.player_id
            ),
            slots AS (
                SELECT gls.player_id, gls.position, COUNT(*) AS n
                FROM game_lineup_slots gls JOIN games g ON g.id = gls.game_id
                WHERE g.season_id = %(season)s AND g.series_id IS NULL
                  AND gls.batting_order IS NOT NULL
                GROUP BY gls.player_id, gls.position
            ),
            top_slot AS (
                SELECT DISTINCT ON (player_id) player_id, position, n
                FROM slots ORDER BY player_id, n DESC, position
            ),
            all_slots AS (
                SELECT player_id, SUM(n) AS n FROM slots GROUP BY player_id
            ),
            prior AS (
                SELECT pss.player_id, SUM(pss.bat_ab) AS ab, SUM(pss.pitch_outs) AS outs
                FROM player_season_stats pss
                JOIN tot ON tot.player_id = pss.player_id
                JOIN seasons s ON s.id = pss.season_id
                WHERE s.year < %(year)s AND NOT pss.is_postseason
                GROUP BY pss.player_id
            )
            SELECT tot.*, p.position AS affinity,
                   top_slot.position AS slot, top_slot.n AS slot_starts,
                   all_slots.n AS all_starts,
                   COALESCE(prior.ab, 0) AS prior_ab, COALESCE(prior.outs, 0) AS prior_outs
            FROM tot
            JOIN players p ON p.id = tot.player_id
            LEFT JOIN top_slot ON top_slot.player_id = tot.player_id
            LEFT JOIN all_slots ON all_slots.player_id = tot.player_id
            LEFT JOIN prior ON prior.player_id = tot.player_id""",
        {"season": season_id, "year": year},
    ).fetchall()
    out = []
    for r in rows:
        c = {k: int(r[k] or 0) for k in _COLUMNS}
        # Without box scores (a backstory season), the position he was made at.
        if r["slot"]:
            position, pos_starts = r["slot"], int(r["slot_starts"])
            starts = int(r["all_starts"])
        else:
            position = (r["affinity"] or "").lower() or None
            pos_starts = starts = c["bat_games_started"]
        c.update(
            player_id=r["player_id"],
            team_id=r["team_id"],
            scope=scope_of.get(r["team_id"], ""),
            position=position,
            pos_starts=pos_starts,
            starts=starts,
            prior_ab=int(r["prior_ab"]),
            prior_outs=int(r["prior_outs"]),
        )
        out.append(c)
    return out


def _decide_regular(
    conn, league_id, season, scope_of, first_season, with_gm, on
) -> None:
    sid = season["id"]
    records = _records(conn, sid)
    games = max((w + l for w, l in records.values()), default=0)
    pct = {t: w / (w + l) for t, (w, l) in records.items() if w + l}
    cands = candidates(conn, sid, season["year"], scope_of)
    rows = awards.regular_awards(cands, games, pct, first_season=first_season)
    if with_gm:
        rows += awards.gm_of_year(_gm_teams(conn, league_id, season, records, scope_of))
    for row in rows:
        _save(conn, sid, row, on)


def _gm_teams(conn, league_id, season, records, scope_of) -> list[dict]:
    prev = conn.execute(
        """SELECT s.id FROM seasons s JOIN league_seasons ls ON ls.season_id = s.id
           WHERE ls.league_id = %s AND s.year < %s
           ORDER BY s.year DESC LIMIT 1""",
        (league_id, season["year"]),
    ).fetchone()
    prev_records = _records(conn, prev["id"]) if prev else {}
    gm_of = {
        r["team_id"]: r["id"]
        for r in conn.execute(
            """SELECT DISTINCT ON (team_id) id, team_id FROM gms
               WHERE league_id = %s AND team_id IS NOT NULL AND fired_at IS NULL
               ORDER BY team_id, created_at DESC""",
            (league_id,),
        ).fetchall()
    }
    titles = set()
    for conf in divisions.load(conn, league_id):
        for div in conf.divisions:
            played = [t for t in div.team_ids if sum(records.get(t, (0, 0)))]
            if played:
                titles.add(
                    max(
                        sorted(played),
                        key=lambda t: records[t][0] / sum(records[t]),
                    )
                )
    out = []
    for team_id, (w, l) in records.items():
        pw, pl = prev_records.get(team_id, (None, None))
        out.append(
            {
                "team_id": team_id,
                "gm_id": gm_of.get(team_id),
                "scope": scope_of.get(team_id, ""),
                "wins": w,
                "losses": l,
                "prev_wins": pw,
                "prev_losses": pl,
                "division_title": team_id in titles,
            }
        )
    return out


# ── Series MVPs ───────────────────────────────────────────────────────────────


def _decide_series(conn, season_id: str, scope_of: dict[str, str]) -> bool:
    """Name the MVP of each Semifinals and Finals series that's been won.
    Returns whether the Finals are decided (and so its MVP named)."""
    rows = conn.execute(
        """SELECT s.id, s.name, g.id AS game_id, g.winner_id, g.game_date
           FROM series s JOIN games g ON g.series_id = s.id
           WHERE s.season_id = %s AND s.name = ANY(%s)
             AND g.completed = 1 AND g.winner_id IS NOT NULL
           ORDER BY s.id, g.game_date, g.id""",
        (season_id, [*SEMIS, FINALS]),
    ).fetchall()
    by_series: dict[str, list[dict]] = {}
    for r in rows:
        by_series.setdefault(r["id"], []).append(dict(r))
    finals_done = False
    for series_id, games in by_series.items():
        wins: dict[str, int] = {}
        played: list[str] = []
        clinched = None
        for g in games:
            wins[g["winner_id"]] = wins.get(g["winner_id"], 0) + 1
            played.append(g["game_id"])
            if wins[g["winner_id"]] >= WINS_NEEDED:
                clinched = g
                break
        if not clinched:
            continue
        name = games[0]["name"]
        winner = clinched["winner_id"]
        if name == FINALS:
            award, scope = "finals_mvp", ""
            finals_done = True
        else:
            award, scope = "semis_mvp", scope_of.get(winner) or name
        lines = _series_lines(conn, played, winner)
        mvp = awards.series_mvp(lines)
        if mvp:
            _save(
                conn,
                season_id,
                {"award": award, "scope": scope, **mvp},
                clinched["game_date"],
            )
    return finals_done


def _series_lines(conn, game_ids: list[str], team_id: str) -> list[dict]:
    # player_game_stats names a game's win, loss, save and hold in the singular.
    singular = {
        "pitch_wins": "pitch_win",
        "pitch_losses": "pitch_loss",
        "pitch_saves": "pitch_save",
        "pitch_holds": "pitch_hold",
    }
    cols = [c for c in _COLUMNS if not c.endswith(("_played", "_started"))]
    sums = ", ".join(f"COALESCE(SUM({singular.get(c, c)}), 0) AS {c}" for c in cols)
    rows = conn.execute(
        f"""SELECT player_id, team_id, {sums}
            FROM player_game_stats
            WHERE game_id = ANY(%s) AND team_id = %s
            GROUP BY player_id, team_id""",
        (game_ids, team_id),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Reading ───────────────────────────────────────────────────────────────────


def for_season(conn, season_id: str) -> list[dict]:
    """The season's awards, in the order awards.AWARDS lists them, each with
    the player's (or GM's) name and the team's."""
    rows = conn.execute(
        """SELECT a.*, p.first_name, p.last_name, t.city, t.mascot,
                  g.display_name AS gm_name, g.is_ai AS gm_is_ai
           FROM season_awards a
           LEFT JOIN players p ON p.id = a.player_id
           LEFT JOIN teams t ON t.id = a.team_id
           LEFT JOIN gms g ON g.id = a.gm_id
           WHERE a.season_id = %s""",
        (season_id,),
    ).fetchall()
    order = {a.key: i for i, a in enumerate(awards.AWARDS)}
    out = [dict(r) for r in rows if r["award"] in order]
    out.sort(key=lambda r: (order[r["award"]], r["scope"]))
    return out


def for_player(conn, player_id: str) -> list[dict]:
    """A player's awards, oldest first: year, award key, name, icon, scope."""
    rows = conn.execute(
        """SELECT a.award, a.scope, a.line, s.year
           FROM season_awards a JOIN seasons s ON s.id = a.season_id
           WHERE a.player_id = %s
           ORDER BY s.year""",
        (player_id,),
    ).fetchall()
    out = []
    for r in rows:
        a = awards.BY_KEY.get(r["award"])
        if a:
            out.append({**dict(r), "name": a.name, "icon": a.icon})
    order = {a.key: i for i, a in enumerate(awards.AWARDS)}
    out.sort(key=lambda r: (r["year"], order[r["award"]]))
    return out
