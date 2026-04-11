# src/stats/loader.py
from typing import List

from src.db.connection import get_connection
from src.db.repositories.player_games import PlayerGameRepository
from src.db.repositories.player_repo import PlayerRepository
from src.player.player_in_game import PlayerInGame
from src.stats.stats import Stats


class StatsLoader:
    """Load and aggregate player statistics using existing repositories"""

    def __init__(self):
        self.conn = get_connection()
        self.player_repo = PlayerRepository(self.conn)
        self.player_game_repo = PlayerGameRepository(self.conn)

    def load_all_players_with_stats(self) -> List[PlayerInGame]:
        """
        Load all players and aggregate their stats across all games.
        Returns PlayerInGame objects with populated game_stats.
        """
        # Get all unique players who have stats
        cursor = self.conn.execute("""
            SELECT DISTINCT player_id 
            FROM player_game_stats
        """)
        player_ids = [row["player_id"] for row in cursor.fetchall()]

        players_with_stats = []

        for player_id in player_ids:
            # Load the player record using repository
            player_record = self.player_repo.get_by_id(player_id)

            if not player_record:
                continue

            # Get all game stats for this player
            all_game_stats = self.player_game_repo.fetch_player_games(player_id)

            # Aggregate stats across all games
            aggregated_stats = Stats()
            for game_stats in all_game_stats:
                aggregated_stats.add(game_stats)

            # Create PlayerInGame with aggregated stats
            player_in_game = PlayerInGame(player_record)
            player_in_game.game_stats = aggregated_stats

            players_with_stats.append(player_in_game)

        return players_with_stats

    def load_season_players_with_stats(self, season_id: str) -> List[PlayerInGame]:
        """
        Load all players and their stats for a specific season.
        Returns PlayerInGame objects with season stats.
        """
        # Get all unique players in this season
        cursor = self.conn.execute(
            """
            SELECT DISTINCT pgs.player_id
            FROM player_game_stats pgs
            JOIN games g ON pgs.game_id = g.id
            WHERE g.season_id = %s AND g.series_id IS NULL
        """,
            (season_id,),
        )

        player_ids = [row["player_id"] for row in cursor.fetchall()]

        players_with_stats = []

        for player_id in player_ids:
            # Load the player record
            player_record = self.player_repo.look_up(player_id)

            if not player_record:
                continue

            # Load season stats using repository
            season_stats = self.player_game_repo.load_season_stats(player_id, season_id)

            # Create PlayerInGame with season stats
            player_in_game = PlayerInGame(player_record)
            player_in_game.game_stats = season_stats.stats

            players_with_stats.append(player_in_game)

        return players_with_stats

    def load_team_players_with_stats(
        self, team_id: str, season_id: str = None
    ) -> List[PlayerInGame]:
        """
        Load all players from a specific team with their stats.

        Args:
            team_id: Team ID
            season_id: Optional season ID to filter by season
        """
        if season_id:
            # Get players on this team in this season
            cursor = self.conn.execute(
                """
                SELECT DISTINCT pgs.player_id
                FROM player_game_stats pgs
                JOIN games g ON pgs.game_id = g.id
                WHERE pgs.team_id = %s AND g.season_id = %s
            """,
                (team_id, season_id),
            )
        else:
            # Get all players who ever played for this team
            cursor = self.conn.execute(
                """
                SELECT DISTINCT player_id
                FROM player_game_stats
                WHERE team_id = %s
            """,
                (team_id,),
            )

        player_ids = [row["player_id"] for row in cursor.fetchall()]

        players_with_stats = []

        for player_id in player_ids:
            player_record = self.player_repo.get_by_id(player_id)

            if not player_record:
                continue

            if season_id:
                # Load season-specific stats
                season_stats = self.player_game_repo.load_season_stats(
                    player_id, season_id
                )
                aggregated_stats = season_stats.stats
            else:
                # Load all-time stats
                all_game_stats = self.player_game_repo.fetch_player_games(player_id)
                aggregated_stats = Stats()
                for game_stats in all_game_stats:
                    aggregated_stats.add(game_stats)

            player_in_game = PlayerInGame(player_record)
            player_in_game.game_stats = aggregated_stats

            players_with_stats.append(player_in_game)

        return players_with_stats

    def close(self):
        """Close database connection"""
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
