# explicit role-based iteration.
class Team:
    def all_players(self):
        return self.players

    def pitchers_used(self):
        return [p for p in self.players if p.season_stats.game_stats.pitching.outs > 0]

    def batters_used(self):
        return [
            p for p in self.players if p.season_stats.game_stats.batting.at_bats > 0
        ]


# Then we can avoid an earlier bug:

# for player in away_team.pitchers_used():
#     logger.info(player.horizontal_pitching_stats("season"))
