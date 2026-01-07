import uuid


class LeagueRepository:
    def __init__(self, conn):
        self.conn = conn

    def create_league(self, league_name: int):
        """
        Create The League

        If you try to re-use a league name, it will just
        return the id of that existing league.
        """
        row = self.conn.execute(
            "SELECT league_id FROM leagues WHERE league_name = ?",
            (league_name,),
        ).fetchone()

        if row:
            return row["league_id"]

        league_id = uuid.uuid4().hex
        self.conn.execute(
            """
            INSERT OR REPLACE INTO leagues (
                league_id, league_name
            )
            VALUES(?, ?)
            """,
            (
                league_id,
                league_name,
            ),
        )
        self.conn.commit()
        return league_id

    def assign_to_league(self, league_id: str, team_id: str):
        self.conn.execute(
            """
            INSERT OR IGNORE INTO league_teams (league_id, team_id)
            VALUES (?, ?)
            """,
            (league_id, team_id),
        )
        self.conn.commit()
