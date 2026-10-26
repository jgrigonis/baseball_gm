# src/db/repositories/player_season_stats_repo.py


class PlayerSeasonStatsRepository:
    def __init__(self, conn):
        self.conn = conn

    def get_max_games_played(self, season_id: str) -> int:
        """Return the max bat_games_played across all players in a season (regular season only)."""
        row = self.conn.execute(
            """SELECT MAX(bat_games_played) as tg FROM player_season_stats
               WHERE season_id = %s AND NOT is_postseason""",
            (season_id,),
        ).fetchone()
        return row["tg"] or 1

    def get_batting_for_league(self, league_id: str, season_id: str) -> list[dict]:
        """Return batting stats for all players in a league (regular season, at least 1 AB)."""
        rows = self.conn.execute(
            """SELECT pss.player_id, p.first_name, p.last_name, t.city, t.mascot, pss.team_id,
                      pss.bat_ab, pss.bat_hits, pss.bat_doubles, pss.bat_triples,
                      pss.bat_home_runs, pss.bat_rbi, pss.bat_runs, pss.bat_walks,
                      pss.bat_strike_outs, pss.bat_stolen_bases, pss.bat_hbp, pss.bat_sac_flys,
                      pss.bat_games_played
               FROM player_season_stats pss
               JOIN players p ON p.id = pss.player_id
               JOIN teams t ON t.id = pss.team_id
               JOIN league_season_teams lst
                 ON lst.team_id = pss.team_id AND lst.season_id = pss.season_id AND lst.league_id = %s
               WHERE pss.season_id = %s AND NOT pss.is_postseason AND pss.bat_ab >= 1""",
            (league_id, season_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_player_season(self, player_id: str, season_id: str) -> dict | None:
        """Return a player's regular season stat row as a dict, or None."""
        row = self.conn.execute(
            """SELECT * FROM player_season_stats
               WHERE player_id = %s AND season_id = %s AND NOT is_postseason""",
            (player_id, season_id),
        ).fetchone()
        return dict(row) if row else None

    def get_team_stats_map(self, season_id: str, team_id: str) -> dict[str, dict]:
        """Return {player_id: stat_dict} for all players on a team in a season (regular season)."""
        rows = self.conn.execute(
            """SELECT player_id,
                      bat_games_played, bat_hits, bat_ab, bat_home_runs, bat_rbi,
                      pitch_games_played, pitch_games_started, pitch_outs, pitch_earned_runs,
                      pitch_wins, pitch_losses, pitch_saves
               FROM player_season_stats
               WHERE season_id = %s AND NOT is_postseason
                 AND player_id IN (
                     SELECT player_id FROM team_players WHERE team_id = %s
                 )""",
            (season_id, team_id),
        ).fetchall()
        return {r["player_id"]: dict(r) for r in rows}

    def get_max_games_played_for_team(
        self, season_id: str, team_id: str, is_postseason: bool = False
    ) -> int:
        """Return the max bat_games_played for a specific team in a season."""
        row = self.conn.execute(
            """SELECT MAX(bat_games_played) as tg FROM player_season_stats
               WHERE season_id = %s AND is_postseason = %s AND team_id = %s""",
            (season_id, is_postseason, team_id),
        ).fetchone()
        return row["tg"] or 0

    def get_for_team(
        self, season_id: str, team_id: str, is_postseason: bool = False
    ) -> list[dict]:
        """Return all player stats with first/last name for a team in a season."""
        rows = self.conn.execute(
            """SELECT p.id as player_id, p.first_name, p.last_name, pss.*
               FROM player_season_stats pss
               JOIN players p ON p.id = pss.player_id
               WHERE pss.season_id = %s AND pss.is_postseason = %s
                 AND pss.team_id = %s""",
            (season_id, is_postseason, team_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_pitching_for_league(self, league_id: str, season_id: str) -> list[dict]:
        """Return pitching stats for all players in a league (regular season, at least 3 outs)."""
        rows = self.conn.execute(
            """SELECT pss.player_id, p.first_name, p.last_name, t.city, t.mascot, pss.team_id,
                      pss.pitch_games_played, pss.pitch_games_started, pss.pitch_wins,
                      pss.pitch_losses, pss.pitch_saves, pss.pitch_outs,
                      pss.pitch_hits, pss.pitch_earned_runs, pss.pitch_walks,
                      pss.pitch_strike_outs, pss.pitch_home_runs
               FROM player_season_stats pss
               JOIN players p ON p.id = pss.player_id
               JOIN teams t ON t.id = pss.team_id
               JOIN league_season_teams lst
                 ON lst.team_id = pss.team_id AND lst.season_id = pss.season_id AND lst.league_id = %s
               WHERE pss.season_id = %s AND NOT pss.is_postseason AND pss.pitch_outs >= 9""",
            (league_id, season_id),
        ).fetchall()
        return [dict(r) for r in rows]
