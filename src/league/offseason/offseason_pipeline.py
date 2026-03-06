# src/league/offseason_pipeline.py

from src.db.repositories.player_repo import PlayerRepository

class OffseasonPipeline:
    def __init__(self, conn):
        self.player_repo = PlayerRepository(conn)
        # ...other repos as steps are built

    def run(self, season_id: str) -> None:
        self._archive(season_id)
        # self._age()
        # self._retire()
        # ...

    def _archive(self, season_id: str) -> None:
        """Step 1: Snapshot all player skills at end of season."""
        players = self.player_repo.get_all_players()
        for player in players:
            self.player_repo.snapshot_skills(player.id, season_id)
        # aggregate_season_stats(season_id)  — TBD
