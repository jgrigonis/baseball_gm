# src/db/repositories/career_repo.py
#
# gm_career_seasons: each person's record, one row per league season
# (src/api/services/career.py keeps it, the profile page reads it).


class CareerRepository:
    def __init__(self, conn):
        self.conn = conn

    def save(self, row: dict) -> None:
        """Insert or update one season. A row that's final is left alone, so
        a season someone left part way keeps the record they left with."""
        self.conn.execute(
            """INSERT INTO gm_career_seasons
                   (user_id, league_id, season_id, league_name, season_year,
                    team_city, team_mascot, wins, losses, division_title,
                    finish, finish_of, playoff_result, sweeps, trades,
                    front_office, final)
               VALUES (%(user_id)s, %(league_id)s, %(season_id)s, %(league_name)s,
                       %(season_year)s, %(team_city)s, %(team_mascot)s, %(wins)s,
                       %(losses)s, %(division_title)s, %(finish)s, %(finish_of)s,
                       %(playoff_result)s, %(sweeps)s, %(trades)s,
                       %(front_office)s, %(final)s)
               ON CONFLICT (user_id, league_id, season_id) DO UPDATE SET
                   league_name    = EXCLUDED.league_name,
                   team_city      = EXCLUDED.team_city,
                   team_mascot    = EXCLUDED.team_mascot,
                   wins           = EXCLUDED.wins,
                   losses         = EXCLUDED.losses,
                   division_title = EXCLUDED.division_title,
                   finish         = EXCLUDED.finish,
                   finish_of      = EXCLUDED.finish_of,
                   sweeps         = EXCLUDED.sweeps,
                   trades         = EXCLUDED.trades,
                   front_office   = EXCLUDED.front_office,
                   playoff_result = EXCLUDED.playoff_result,
                   final          = EXCLUDED.final,
                   updated_at     = NOW()
               WHERE NOT gm_career_seasons.final""",
            row,
        )

    def save_head_to_head(self, row: dict) -> None:
        """Insert or update one person's record against another in a
        season (gm_head_to_head). Final rows are left alone."""
        self.conn.execute(
            """INSERT INTO gm_head_to_head
                   (user_id, opponent_id, league_id, season_id, league_name,
                    season_year, team_city, team_mascot, opponent_city,
                    opponent_mascot, wins, losses, series_round, series_won, final)
               VALUES (%(user_id)s, %(opponent_id)s, %(league_id)s, %(season_id)s,
                       %(league_name)s, %(season_year)s, %(team_city)s,
                       %(team_mascot)s, %(opponent_city)s, %(opponent_mascot)s,
                       %(wins)s, %(losses)s, %(series_round)s, %(series_won)s,
                       %(final)s)
               ON CONFLICT (user_id, opponent_id, league_id, season_id) DO UPDATE SET
                   league_name  = EXCLUDED.league_name,
                   wins         = EXCLUDED.wins,
                   losses       = EXCLUDED.losses,
                   series_round = EXCLUDED.series_round,
                   series_won   = EXCLUDED.series_won,
                   final        = EXCLUDED.final,
                   updated_at   = NOW()
               WHERE NOT gm_head_to_head.final""",
            row,
        )

    def head_to_head_for(self, user_id: str) -> list[dict]:
        """The person's seasons against other people, newest first, with
        the opponent's username and name."""
        rows = self.conn.execute(
            """SELECT h.*, u.username AS opponent_username,
                      u.display_name AS opponent_name
               FROM gm_head_to_head h JOIN users u ON u.id = h.opponent_id
               WHERE h.user_id = %s
               ORDER BY h.season_year DESC, h.league_name""",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def final_season_ids(self, user_id: str, league_id: str) -> set[str]:
        rows = self.conn.execute(
            """SELECT season_id FROM gm_career_seasons
               WHERE user_id = %s AND league_id = %s AND final""",
            (user_id, league_id),
        ).fetchall()
        return {r["season_id"] for r in rows}

    def rename_league(self, league_id: str, name: str) -> None:
        self.conn.execute(
            "UPDATE gm_career_seasons SET league_name = %s WHERE league_id = %s",
            (name, league_id),
        )
        self.conn.execute(
            "UPDATE gm_head_to_head SET league_name = %s WHERE league_id = %s",
            (name, league_id),
        )

    def for_user(self, user_id: str) -> list[dict]:
        """Every season the person has played, newest first."""
        rows = self.conn.execute(
            """SELECT * FROM gm_career_seasons WHERE user_id = %s
               ORDER BY season_year DESC, league_name""",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
