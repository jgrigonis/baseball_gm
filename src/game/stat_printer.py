from src.player.player_formatters import PlayerTableFormatter


def output_stats(game):
    """Handle the stats for the game.

    This function should live elsewhere
    """
    game.logger.info(
        PlayerTableFormatter.horizontal_stat_header(
            game.home.city + " " + game.home.mascot
        )
    )
    for player in game.home.lineup:
        game.logger.info(PlayerTableFormatter.horizontal_stats(player))

    game.logger.info(
        PlayerTableFormatter.horizontal_stat_header(
            game.away.city + " " + game.away.mascot
        )
    )
    for player in game.away.lineup:
        game.logger.info(PlayerTableFormatter.horizontal_stats(player))
    game.logger.info("-" * 100)
    game.logger.info(
        PlayerTableFormatter.horizontal_pitching_stat_header(
            game.home.city + " " + game.home.mascot
        )
    )
    for player in game.home.players:
        if player.game_stats.pitching.ip_float > 0:
            game.logger.info(PlayerTableFormatter.horizontal_pitching_stats(player))

    game.logger.info(
        PlayerTableFormatter.horizontal_pitching_stat_header(
            game.away.city + " " + game.away.mascot
        )
    )
    for player in game.away.players:
        if player.game_stats.pitching.ip_float > 0:
            game.logger.info(PlayerTableFormatter.horizontal_pitching_stats(player))
    game.logger.info("-" * 100)
