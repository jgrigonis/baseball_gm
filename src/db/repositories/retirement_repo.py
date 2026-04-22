# src/db/repositories/retirement_repo.py


class RetirementRepository:
    def __init__(self, conn):
        self.conn = conn

    def retire_player(self, player_id: str, league_id: str, season_id: str, team_id: str) -> None:
        """Inserts a player into the player_retirements table.

        player_id: the player id to be retired.
        league_id: the league they are retiring from.
        season_id: the current season that is running.
        team_id: the former team they are retiring from.
        """
        self.conn.execute(
            """INSERT INTO player_retirements
                    (player_id, league_id, season_id, former_team_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING""",
            (
                player_id,
                league_id,
                season_id,
                team_id,
            ),
        )
