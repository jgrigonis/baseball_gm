# src/db/repositories/happiness_repo.py
"""
Player happiness in the database (rules in src/player/happiness.py,
plan in plans/player-happiness.md).

- player_personality  each player's type, drive weights, traits, climate
- player_moods        each player's mood per season, and why

update_if_due runs from the game loop: once a league week, it works out
every rostered player's satisfaction on each drive from what the league
already stores (contracts, the standings, team states, lineups, rotations,
bullpen roles, past seasons, trades, All-Stars, the team pool's market and
climate) and moves his mood a step toward where that points.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from psycopg.types.json import Jsonb

from src.league import team_pool
from src.player import contracts as ct
from src.player import happiness as hp
from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills
from src.player.player_value import role_rating

UPDATE_EVERY_DAYS = 7
USAGE_WINDOW_GAMES = 20
HISTORY_SEASONS = 5
ROSTERED = ("26man", "40man", "minors")


def _day(value) -> date:
    return date.fromisoformat(str(value)[:10])


class HappinessRepository:
    def __init__(self, conn, league_id: str):
        self.conn = conn
        self.league_id = league_id

    # ── Personalities ──────────────────────────────────────────────────────

    def personalities(self, player_ids) -> dict[str, hp.Personality]:
        """Each player's personality, made (and stored) for anyone missing
        one."""
        ids = list(player_ids)
        if not ids:
            return {}
        rows = self.conn.execute(
            "SELECT * FROM player_personality WHERE player_id = ANY(%s)", (ids,)
        ).fetchall()
        out = {r["player_id"]: hp.Personality.from_row(dict(r)) for r in rows}
        missing = [pid for pid in ids if pid not in out]
        if missing:
            with self.conn.cursor() as cur:
                cur.executemany(
                    """INSERT INTO player_personality
                           (player_id, type, drives, traits, climate)
                       VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                    [
                        (
                            pid,
                            (p := hp.personality_for(pid)).type,
                            Jsonb(p.drives),
                            Jsonb(p.traits),
                            p.climate,
                        )
                        for pid in missing
                    ],
                )
            for pid in missing:
                out[pid] = hp.personality_for(pid)
        return out

    # ── Moods ──────────────────────────────────────────────────────────────

    def mood(self, player_id: str, season_id: str | None = None) -> dict | None:
        """His newest mood row (this season's if season_id is given)."""
        if season_id:
            row = self.conn.execute(
                "SELECT * FROM player_moods WHERE player_id = %s AND season_id = %s",
                (player_id, season_id),
            ).fetchone()
        else:
            row = self.conn.execute(
                """SELECT m.* FROM player_moods m JOIN seasons s ON s.id = m.season_id
                   WHERE m.player_id = %s ORDER BY s.year DESC LIMIT 1""",
                (player_id,),
            ).fetchone()
        return dict(row) if row else None

    def moods(self, player_ids, season_id: str) -> dict[str, dict]:
        ids = list(player_ids)
        if not ids:
            return {}
        rows = self.conn.execute(
            "SELECT * FROM player_moods WHERE player_id = ANY(%s) AND season_id = %s",
            (ids, season_id),
        ).fetchall()
        return {r["player_id"]: dict(r) for r in rows}

    def last_update(self, season_id: str) -> str | None:
        row = self.conn.execute(
            """SELECT MAX(updated_on) AS d FROM player_moods
               WHERE league_id = %s AND season_id = %s""",
            (self.league_id, season_id),
        ).fetchone()
        return row["d"] if row else None

    def update_if_due(self, season_id: str, as_of: date) -> bool:
        """Update everyone's mood if a week has passed since the last
        update this season (or there hasn't been one)."""
        last = self.last_update(season_id)
        if last and (as_of - _day(last)).days < UPDATE_EVERY_DAYS:
            return False
        self.update(season_id, as_of)
        return True

    def update(self, season_id: str, as_of: date) -> int:
        """Work out every rostered player's mood as of this date. Returns
        how many were updated."""
        teams = self._teams(season_id)
        if not teams:
            return 0
        team_ids = list(teams)
        players = self._players(team_ids)
        if not players:
            return 0
        ids = list(players)
        year = self._year(season_id)

        pers = self.personalities(ids)
        contracts = self._contracts(ids, year)
        records = self._records(season_id, team_ids)
        states = self._states(season_id)
        usage = self._usage(season_id, team_ids, players, as_of)
        history = self._history(season_id, team_ids)
        trades = self._trades(season_id, team_ids)
        all_stars = self._all_stars(season_id, ids)
        previous = self._previous_moods(season_id, ids)
        current = self.moods(ids, season_id)
        league_regions = {t["region"] for t in teams.values() if t["region"]}

        # Rank each player among his team's hitters or pitchers.
        ranks: dict[str, tuple[int, int]] = {}
        by_group = defaultdict(list)
        for pid, p in players.items():
            by_group[(p["team_id"], p["pitcher"])].append(pid)
        for group in by_group.values():
            group.sort(key=lambda pid: -players[pid]["rating"])
            for i, pid in enumerate(group):
                ranks[pid] = (i, len(group))

        rows = []
        for pid, p in players.items():
            team = teams[p["team_id"]]
            person = pers[pid]
            u = usage.get(pid, hp.Usage())
            rank, size = ranks[pid]
            c = contracts.get(pid)
            worth = ct.prime_salary(p["rating"], p["kind"]) * ct.age_factor(p["age"])
            wins, losses = records.get(p["team_id"], (0, 0))
            hist = history.get(p["team_id"])
            sats = {
                "money": hp.money(
                    c["salary"] if c else None,
                    worth,
                    rookie=bool(c and c["kind"] == "rookie"),
                ),
                "winning": hp.winning(wins, losses, states.get(p["team_id"])),
                "impact": hp.impact(
                    p["pitcher"],
                    p["affinity"],
                    rank,
                    size,
                    u,
                    person.traits["ego"],
                ),
                "position": hp.position(p["pitcher"], p["affinity"], u),
                "stability": hp.stability(
                    hist[0] if hist else None,
                    hist[1] if hist else 0,
                    trades.get(p["team_id"], 0),
                ),
                "location": hp.location(
                    p["home_region"],
                    team["region"],
                    team["climate"],
                    league_regions,
                    person.climate,
                ),
                "fame": hp.fame(team["market"], pid in all_stars),
            }
            goal = hp.target(person, p["age"], sats)
            now = current.get(pid)
            if now is None:
                before = previous.get(pid)
                start = goal if before is None else 0.5 * before + 0.5 * goal
                mood = start
            elif now["team_id"] != p["team_id"]:
                mood = 0.5 * now["mood"] + 0.5 * goal  # a fresh start somewhere new
            else:
                mood = hp.step(now["mood"], goal, person.traits["temper"])
            lines = hp.on_his_mind(
                person, p["age"], sats, p["affinity"], p["home_region"]
            )
            detail = {
                "drives": {d: [round(s, 3), why] for d, (s, why) in sats.items()},
                "lines": lines,
            }
            rows.append(
                (
                    pid,
                    season_id,
                    self.league_id,
                    p["team_id"],
                    round(mood, 4),
                    round(goal, 4),
                    Jsonb(detail),
                    as_of.isoformat(),
                )
            )
        with self.conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO player_moods (
                    player_id, season_id, league_id, team_id, mood, target,
                    detail, updated_on
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (player_id, season_id) DO UPDATE SET
                    league_id = EXCLUDED.league_id, team_id = EXCLUDED.team_id,
                    mood = EXCLUDED.mood, target = EXCLUDED.target,
                    detail = EXCLUDED.detail, updated_on = EXCLUDED.updated_on
                """,
                rows,
            )
        return len(rows)

    # ── What the league already knows ──────────────────────────────────────

    def _teams(self, season_id: str) -> dict[str, dict]:
        rows = self.conn.execute(
            """SELECT t.id, t.city, t.mascot FROM league_season_teams lst
               JOIN teams t ON t.id = lst.team_id
               WHERE lst.league_id = %s AND lst.season_id = %s""",
            (self.league_id, season_id),
        ).fetchall()
        out = {}
        for r in rows:
            pool = team_pool.get(r["city"], r["mascot"]) or team_pool.by_city(r["city"])
            out[r["id"]] = {
                "region": pool.region if pool else None,
                "climate": pool.climate if pool else team_pool.TEMPERATE,
                "market": pool.market if pool else 3,
            }
        return out

    def _players(self, team_ids: list[str]) -> dict[str, dict]:
        rows = self.conn.execute(
            """SELECT p.*, sk.*, tp.team_id, ps.status
               FROM team_players tp
               JOIN players p ON p.id = tp.player_id
               JOIN player_skills sk ON sk.player_id = p.id
               JOIN player_status ps ON ps.player_id = p.id
               WHERE tp.team_id = ANY(%s) AND ps.status = ANY(%s)""",
            (team_ids, list(ROSTERED)),
        ).fetchall()
        out = {}
        for r in rows:
            rec = PlayerRecord(
                id=r["id"],
                first_name=r["first_name"],
                last_name=r["last_name"],
                bats=r["bats"],
                throws=r["throws"],
                position=r["position"],
                skills=PlayerSkills.from_db_row(r),
            )
            pitcher = rec.is_pitcher()
            out[rec.id] = {
                "team_id": r["team_id"],
                "status": r["status"],
                "pitcher": pitcher,
                "kind": "pitcher" if pitcher else "hitter",
                "affinity": r["position"] or ("sp" if pitcher else "dh"),
                "age": rec.age,
                "rating": role_rating(rec),
                "home_region": r.get("home_region"),
            }
        return out

    def _year(self, season_id: str) -> int | None:
        row = self.conn.execute(
            "SELECT year FROM seasons WHERE id = %s", (season_id,)
        ).fetchone()
        return row["year"] if row else None

    def _contracts(self, ids: list[str], year: int | None) -> dict[str, dict]:
        if year is None:
            return {}
        # Imported here: contract_repo imports player_value, which is fine,
        # but keeps this module's imports light for the game loop.
        from src.db.repositories.contract_repo import ContractRepository

        return ContractRepository(self.conn).active_for(ids, year)

    def _records(self, season_id: str, team_ids: list[str]) -> dict[str, tuple]:
        rows = self.conn.execute(
            """SELECT t.team_id,
                      COUNT(*) FILTER (WHERE g.winner_id = t.team_id) AS wins,
                      COUNT(*) FILTER (WHERE g.winner_id IS NOT NULL
                                         AND g.winner_id <> t.team_id) AS losses
               FROM games g
               CROSS JOIN LATERAL (VALUES (g.home_team_id), (g.away_team_id))
                   AS t(team_id)
               WHERE g.season_id = %s AND g.completed = 1
                 AND t.team_id = ANY(%s) AND g.series_id IS NULL
               GROUP BY t.team_id""",
            (season_id, team_ids),
        ).fetchall()
        return {r["team_id"]: (r["wins"], r["losses"]) for r in rows}

    def _states(self, season_id: str) -> dict[str, str]:
        from src.db.repositories.team_state_repo import TeamStateRepository

        latest = TeamStateRepository(self.conn).latest(self.league_id, season_id)
        return {tid: r["state"] for tid, r in latest.items()}

    def _usage(
        self, season_id: str, team_ids: list[str], players: dict, as_of: date
    ) -> dict[str, hp.Usage]:
        """Each player's starts, batting order and positions over his team's
        last few games, and pitchers' current roles."""
        since = (as_of - timedelta(days=USAGE_WINDOW_GAMES + 10)).isoformat()
        games = self.conn.execute(
            """SELECT g.id, g.game_date, g.home_team_id, g.away_team_id FROM games g
               WHERE g.season_id = %s AND g.completed = 1 AND g.game_date >= %s
                 AND g.game_date <= %s
                 AND (g.home_team_id = ANY(%s) OR g.away_team_id = ANY(%s))
               ORDER BY g.game_date DESC, g.id""",
            (season_id, since, as_of.isoformat(), team_ids, team_ids),
        ).fetchall()
        window: dict[str, list[str]] = defaultdict(list)  # team -> game ids
        for g in games:
            for tid in (g["home_team_id"], g["away_team_id"]):
                if len(window[tid]) < USAGE_WINDOW_GAMES:
                    window[tid].append(g["id"])
        game_ids = sorted({gid for gids in window.values() for gid in gids})
        usage = {
            pid: hp.Usage(
                team_games=len(window.get(p["team_id"], [])),
                minors=p["status"] == "minors",
            )
            for pid, p in players.items()
        }
        if game_ids:
            in_window = {(tid, gid) for tid, gids in window.items() for gid in gids}
            slots = self.conn.execute(
                """SELECT game_id, team_id, player_id, position, batting_order
                   FROM game_lineup_slots
                   WHERE game_id = ANY(%s) AND is_pitcher = 0""",
                (game_ids,),
            ).fetchall()
            for s in slots:
                u = usage.get(s["player_id"])
                if u is None or (s["team_id"], s["game_id"]) not in in_window:
                    continue
                if players[s["player_id"]]["team_id"] != s["team_id"]:
                    continue
                u.starts += 1
                if s["batting_order"]:
                    u.slots.append(int(s["batting_order"]))
                u.positions.append(s["position"])

        rotation = self.conn.execute(
            """SELECT player_id, team_id FROM team_rotations
               WHERE season_id = %s AND end_date IS NULL AND team_id = ANY(%s)""",
            (season_id, team_ids),
        ).fetchall()
        for r in rotation:
            u = usage.get(r["player_id"])
            if u is not None and players[r["player_id"]]["team_id"] == r["team_id"]:
                u.in_rotation = True
        roles = self.conn.execute(
            """SELECT player_id, team_id, role FROM bullpen_roles
               WHERE season_id = %s AND end_date IS NULL AND team_id = ANY(%s)""",
            (season_id, team_ids),
        ).fetchall()
        for r in roles:
            u = usage.get(r["player_id"])
            if u is not None and players[r["player_id"]]["team_id"] == r["team_id"]:
                u.bullpen_role = r["role"]
        return usage

    def _history(self, season_id: str, team_ids: list[str]) -> dict[str, tuple]:
        """Each team's win % over the league's last few seasons before this
        one (backstory seasons count), and how many seasons that is."""
        rows = self.conn.execute(
            """WITH past AS (
                   SELECT s.id FROM seasons s
                   JOIN league_seasons ls ON ls.season_id = s.id
                   WHERE ls.league_id = %s
                     AND s.year < (SELECT year FROM seasons WHERE id = %s)
                   ORDER BY s.year DESC LIMIT %s)
               SELECT t.team_id, COUNT(DISTINCT g.season_id) AS seasons,
                      COUNT(*) FILTER (WHERE g.winner_id = t.team_id) AS wins,
                      COUNT(*) FILTER (WHERE g.winner_id IS NOT NULL) AS games
               FROM games g
               CROSS JOIN LATERAL (VALUES (g.home_team_id), (g.away_team_id))
                   AS t(team_id)
               WHERE g.season_id IN (SELECT id FROM past) AND g.completed = 1
                 AND t.team_id = ANY(%s)
               GROUP BY t.team_id""",
            (self.league_id, season_id, HISTORY_SEASONS, team_ids),
        ).fetchall()
        return {
            r["team_id"]: (r["wins"] / r["games"], r["seasons"])
            for r in rows
            if r["games"]
        }

    def _trades(self, season_id: str, team_ids: list[str]) -> dict[str, int]:
        """Trades each team has made this season and last."""
        rows = self.conn.execute(
            """WITH recent AS (
                   SELECT s.id FROM seasons s
                   JOIN league_seasons ls ON ls.season_id = s.id
                   WHERE ls.league_id = %s
                     AND s.year <= (SELECT year FROM seasons WHERE id = %s)
                   ORDER BY s.year DESC LIMIT 2)
               SELECT t.team_id, COUNT(*) AS n
               FROM trade_offers o
               CROSS JOIN LATERAL (VALUES (o.from_team_id), (o.to_team_id))
                   AS t(team_id)
               WHERE o.league_id = %s AND o.status = 'accepted'
                 AND o.season_id IN (SELECT id FROM recent)
                 AND t.team_id = ANY(%s)
               GROUP BY t.team_id""",
            (self.league_id, season_id, self.league_id, team_ids),
        ).fetchall()
        return {r["team_id"]: r["n"] for r in rows}

    def _all_stars(self, season_id: str, ids: list[str]) -> set[str]:
        """All-Stars this season or last."""
        rows = self.conn.execute(
            """WITH recent AS (
                   SELECT s.id FROM seasons s
                   JOIN league_seasons ls ON ls.season_id = s.id
                   WHERE ls.league_id = %s
                     AND s.year <= (SELECT year FROM seasons WHERE id = %s)
                   ORDER BY s.year DESC LIMIT 2)
               SELECT DISTINCT player_id FROM all_stars
               WHERE season_id IN (SELECT id FROM recent) AND player_id = ANY(%s)""",
            (self.league_id, season_id, ids),
        ).fetchall()
        return {r["player_id"] for r in rows}

    def _previous_moods(self, season_id: str, ids: list[str]) -> dict[str, float]:
        """Each player's mood at the end of his last season before this
        one, which carries over at half strength."""
        rows = self.conn.execute(
            """SELECT DISTINCT ON (m.player_id) m.player_id, m.mood
               FROM player_moods m JOIN seasons s ON s.id = m.season_id
               WHERE m.player_id = ANY(%s)
                 AND s.year < (SELECT year FROM seasons WHERE id = %s)
               ORDER BY m.player_id, s.year DESC""",
            (ids, season_id),
        ).fetchall()
        return {r["player_id"]: r["mood"] for r in rows}
