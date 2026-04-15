# src/db/repositories/player_season_stats_repo.py


class PlayerSeasonStatsRepository:
    def __init__(self, conn):
        self.conn = conn

    def get_max_games_played(self, season_id: str) -> int:
        """Return the max bat_games_played across all players in a season (regular season only)."""
        row = self.conn.execute(
            """SELECT MAX(bat_games_played) as tg FROM player_season_stats
               WHERE season_id = %s AND is_postseason = 0""",
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
               WHERE pss.season_id = %s AND pss.is_postseason = 0 AND pss.bat_ab >= 1""",
            (league_id, season_id),
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
               WHERE pss.season_id = %s AND pss.is_postseason = 0 AND pss.pitch_outs >= 9""",
            (league_id, season_id),
        ).fetchall()
        return [dict(r) for r in rows]
