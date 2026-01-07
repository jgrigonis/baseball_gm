# season_stats = season_repo.load_player_season_stats(
#     player_id=player.id,
#     season=current_season
# )


import uuid


class SeasonRepository:
    def __init__(self, conn):
        self.conn = conn

    def create_season(self, league_id: int, year: int):
        """
        Create The Season

        If you try to create an existing year seaons in the
        same league, it will just
        return the id of that existing season.
        """
        row = self.conn.execute(
            "SELECT id FROM seasons WHERE year = ? and league_id = ?",
            (year, league_id),
        ).fetchone()

        if row:
            return row["id"]

        season_id = uuid.uuid4().hex
        self.conn.execute(
            """
            INSERT OR REPLACE INTO seasons (
                season_id, league_id, year
            )
            VALUES(?, ?, ?)
            """,
            (
                season_id,
                league_id,
                year,
            ),
        )
        self.conn.commit()
        return season_id
