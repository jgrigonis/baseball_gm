# src/api/services/records/play.py
"""
Keeping the stored records (single games and streaks) up to date as games
are played, and the news when one falls.

update_league() runs after every sim job, like the news feed. Each played
season's record_progress row says the last day it has read; it picks up
from there, so a day or a whole season comes out the same. A league seen
for the first time is caught up quietly (no news for old games): its
backstory is replayed (replay.py), then every day already played is read.

Regular season only: the postseason's records are worked out from the box
scores on the page, since there are only a few dozen games a year.
"""

from __future__ import annotations

import logging
import random

from src.api.services.records import defs, feats, news
from src.api.services.records.defs import Run

log = logging.getLogger(__name__)


def update_league(conn, league_id: str) -> None:
    """Bring the league's stored records up to date. In a savepoint, so a
    problem is logged and never undoes the sim that called it."""
    try:
        with conn.transaction():
            _update(conn, league_id)
    except Exception:
        log.exception("League %s: couldn't update the record book", league_id)


def _update(conn, league_id: str) -> None:
    league = conn.execute(
        "SELECT state, records_seeded FROM leagues WHERE id = %s", (league_id,)
    ).fetchone()
    if not league or league["state"] == "lobby":
        return
    quiet = not league["records_seeded"]
    if quiet:
        from src.api.services.records import replay

        replay.seed_league(conn, league_id, random.Random(league_id))
        conn.execute(
            "UPDATE leagues SET records_seeded = TRUE WHERE id = %s", (league_id,)
        )
    for season in _open_seasons(conn, league_id):
        _catch_up(conn, league_id, season, quiet)


def _open_seasons(conn, league_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT s.id, s.year, rp.through FROM seasons s
           JOIN league_seasons ls ON ls.season_id = s.id
           LEFT JOIN record_progress rp
             ON rp.league_id = ls.league_id AND rp.season_id = s.id
           WHERE ls.league_id = %s AND NOT s.is_backstory
             AND NOT COALESCE(rp.closed, FALSE)
           ORDER BY s.year""",
        (league_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _catch_up(conn, league_id: str, season: dict, quiet: bool) -> None:
    sid = season["id"]
    through = season["through"] or ""
    dates = conn.execute(
        """SELECT MAX(game_date) FILTER (WHERE completed = 1) AS last,
                  COUNT(*) FILTER (WHERE completed IS DISTINCT FROM 1) AS left_to_play,
                  COUNT(*) AS games
           FROM games WHERE season_id = %s AND series_id IS NULL""",
        (sid,),
    ).fetchone()
    last = dates["last"]
    over = dates["games"] > 0 and dates["left_to_play"] == 0
    if last and last > through:
        reader = _Reader(conn, league_id, sid, season["year"], quiet)
        reader.since, reader.until = through, last
        reader.games(through, last)
        reader.streaks(through, last, over)
        reader.finish()
        through = last
    if over:
        # Over: no streak is still going.
        _end_streaks(conn, league_id, sid)
    conn.execute(
        """INSERT INTO record_progress (league_id, season_id, through, closed)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (league_id, season_id) DO UPDATE
           SET through = EXCLUDED.through, closed = EXCLUDED.closed""",
        (league_id, sid, through, over),
    )
    if over and not quiet:
        news.season_over(conn, league_id, sid, last)


def _end_streaks(conn, league_id: str, season_id: str) -> None:
    conn.execute(
        """UPDATE record_feats SET active = FALSE
           WHERE league_id = %s AND season_id = %s AND kind = 'streak' AND active""",
        (league_id, season_id),
    )


class _Reader:
    """Reads the regular-season games after ``since`` through ``until``."""

    def __init__(self, conn, league_id, season_id, year, quiet):
        self.conn = conn
        self.league_id = league_id
        self.season_id = season_id
        self.year = year
        self.quiet = quiet
        self.rows: list[dict] = []
        self.broken: list[tuple] = []  # (kind, stat, feat, old record)
        self.since = self.until = ""

    # ── Single games ──────────────────────────────────────────────────────

    def games(self, since: str, until: str) -> None:
        cols = ", ".join(
            f"COALESCE(pgs.{s.column}, 0) AS {s.column}" for s in defs.GAME_STATS
        )
        rows = self.conn.execute(
            f"""SELECT pgs.player_id, pgs.team_id, pgs.opponent_team_id, g.id AS game_id,
                       g.game_date, g.innings_played, {cols},
                       COALESCE(pgs.bat_ab, 0) AS ab, COALESCE(pgs.bat_walks, 0) AS bb,
                       COALESCE(pgs.bat_hbp, 0) AS hbp, COALESCE(pgs.bat_sac_flys, 0) AS sf,
                       COALESCE(pgs.bat_hits, 0) AS h, COALESCE(pgs.bat_home_runs, 0) AS hr,
                       COALESCE(pgs.bat_game_played, 0) AS bat_played,
                       COALESCE(pgs.pitch_win, 0) AS pw, COALESCE(pgs.pitch_loss, 0) AS pl
                FROM player_game_stats pgs JOIN games g ON g.id = pgs.game_id
                WHERE g.season_id = %s AND g.series_id IS NULL AND g.completed = 1
                  AND g.game_date > %s AND g.game_date <= %s
                ORDER BY g.game_date, g.id""",
            (self.season_id, since, until),
        ).fetchall()  # fmt: skip
        self.rows = rows
        keeper = feats.Keeper(self.conn, self.league_id, "game")
        marks = news.marks(self.conn, self.league_id, "game")
        out = []
        for r in rows:
            for s in defs.GAME_STATS:
                v = int(r[s.column])
                if not keeper.worth(s.key, r["team_id"], v, s.keep):
                    continue
                feat = {
                    "league_id": self.league_id,
                    "kind": "game",
                    "stat": s.key,
                    "key": f"g:{s.key}:{r['player_id']}:{r['game_id']}",
                    "value": v,
                    "subject": r["player_id"],
                    "player_id": r["player_id"],
                    "team_id": r["team_id"],
                    "season_id": self.season_id,
                    "year": self.year,
                    "game_id": r["game_id"],
                    "on_date": r["game_date"],
                    "opp_team_id": r["opponent_team_id"],
                    "innings": r["innings_played"],
                    "source": "played",
                    "active": False,
                }
                out.append(feat)
                record = marks.get(s.key)
                if record and (
                    v > record[0]
                    or (v == record[0] and v >= defs.RARE_TIE.get(s.key, 10**9))
                ):
                    self.broken.append(("game", s.key, feat, record[0]))
                if not record or v > record[0]:
                    marks[s.key] = (v, feat["key"])
                keeper.add(s.key, r["team_id"], v)
        feats.save(self.conn, out)

    # ── Streaks ───────────────────────────────────────────────────────────

    def streaks(self, since: str, until: str, over: bool) -> None:
        runs = self._load_runs()
        keeper = feats.Keeper(self.conn, self.league_id, "streak")
        marks = news.marks(self.conn, self.league_id, "streak")
        saved = {
            r["key"]
            for r in self.conn.execute(
                """SELECT key FROM record_feats
                   WHERE league_id = %s AND season_id = %s AND kind = 'streak'""",
                (self.league_id, self.season_id),
            ).fetchall()
        }
        out: dict[str, dict] = {}

        def touch(stat: defs.StreakStat, subject, run: Run, active: bool):
            """A run long enough to keep: save it (going or over)."""
            if run.length < stat.keep:
                return
            key = f"s:{stat.key}:{subject}:{self.season_id}:{run.start}"
            # One already saved while it was going is always brought up to date.
            if key not in saved and not keeper.worth(
                stat.key, run.team_id, run.length, stat.keep
            ):
                return
            feat = {
                "league_id": self.league_id,
                "kind": "streak",
                "stat": stat.key,
                "key": key,
                "value": run.length,
                "subject": subject,
                "player_id": None if stat.team else subject,
                "team_id": run.team_id,
                "season_id": self.season_id,
                "year": self.year,
                "game_id": run.last_game,
                "on_date": run.last,
                "start_date": run.start,
                "source": "played",
                "active": active,
            }
            out[key] = feat
            saved.add(key)
            record = marks.get(stat.key)
            if record and run.length > record[0] and record[1] != key:
                self.broken.append(("streak", stat.key, feat, record[0]))
            if not record or run.length > record[0]:
                marks[stat.key] = (run.length, key)
            if not active:
                keeper.add(stat.key, run.team_id, run.length)

        def feed(stat, subject, outcome, date, game_id, team_id):
            run = runs.setdefault((stat.key, subject), Run())
            ended = run.feed(outcome, date, game_id, team_id)
            if ended:
                touch(stat, subject, ended, False)
            elif outcome == defs.EXTEND:
                touch(stat, subject, run, True)

        by = defs.STREAK_BY_KEY
        for r in self.rows:
            if r["bat_played"]:
                g = {"ab": r["ab"], "h": r["h"], "hr": r["hr"], "bb": r["bb"],
                     "hbp": r["hbp"], "sf": r["sf"]}  # fmt: skip
                for key, outcome in defs.hitter_outcomes(g).items():
                    feed(by[key], r["player_id"], outcome, r["game_date"],
                         r["game_id"], r["team_id"])  # fmt: skip
            outcome = defs.pitcher_outcome(r["pw"], r["pl"])
            if outcome != defs.SKIP:
                feed(by["pwin"], r["player_id"], outcome, r["game_date"],
                     r["game_id"], r["team_id"])  # fmt: skip
        for t in self.conn.execute(
            """SELECT tgs.team_id, tgs.win, g.game_date, g.id AS game_id
               FROM games g JOIN team_game_stats tgs ON tgs.game_id = g.id
               WHERE g.season_id = %s AND g.series_id IS NULL AND g.completed = 1
                 AND g.game_date > %s AND g.game_date <= %s
               ORDER BY g.game_date, g.id""",
            (self.season_id, since, until),
        ).fetchall():
            won = defs.EXTEND if t["win"] else defs.BREAK
            feed(
                by["twin"],
                t["team_id"],
                won,
                t["game_date"],
                t["game_id"],
                t["team_id"],
            )
            feed(
                by["tloss"],
                t["team_id"],
                -won,
                t["game_date"],
                t["game_id"],
                t["team_id"],
            )
        if over:
            for (key, subject), run in runs.items():
                if run.length:
                    touch(by[key], subject, run, False)
        feats.save(self.conn, list(out.values()))
        self._save_runs(runs)

    def _load_runs(self) -> dict[tuple[str, str], Run]:
        rows = self.conn.execute(
            """SELECT stat, subject, team_id, length, start_date, last_date,
                      start_game, last_game
               FROM record_runs WHERE league_id = %s AND season_id = %s""",
            (self.league_id, self.season_id),
        ).fetchall()
        return {
            (r["stat"], r["subject"]): Run(
                r["length"],
                r["start_date"],
                r["last_date"],
                r["start_game"],
                r["last_game"],
                r["team_id"],
            )  # fmt: skip
            for r in rows
        }

    def _save_runs(self, runs: dict[tuple[str, str], Run]) -> None:
        self.conn.execute(
            "DELETE FROM record_runs WHERE league_id = %s AND season_id = %s",
            (self.league_id, self.season_id),
        )
        rows = [
            (self.league_id, self.season_id, stat, subject, run.team_id, run.length,
             run.start, run.last, run.start_game, run.last_game)
            for (stat, subject), run in runs.items()
            if run.length
        ]  # fmt: skip
        if rows:
            with self.conn.cursor() as cur:
                cur.executemany(
                    """INSERT INTO record_runs (league_id, season_id, stat, subject,
                           team_id, length, start_date, last_date, start_game, last_game)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    rows,
                )

    def finish(self) -> None:
        if self.quiet:
            return
        news.broken(self.conn, self.league_id, self.season_id, self.broken)
        news.season_progress(
            self.conn, self.league_id, self.season_id, self.since, self.until
        )
