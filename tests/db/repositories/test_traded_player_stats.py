# tests/db/repositories/test_traded_player_stats.py
"""A player traded mid-season has a stats row per team. Leaders, his player
card and roster cards show his totals; the team stats pages keep the split."""

from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository


def _row(db, player, season, team, ab, hits, hr, outs=0):
    db.execute(
        """INSERT INTO player_season_stats
               (player_id, season_id, team_id, is_postseason, bat_games_played,
                bat_ab, bat_hits, bat_home_runs, pitch_outs)
           VALUES (%s, %s, %s, FALSE, 10, %s, %s, %s, %s)""",
        (player.id, season.id, team.id, ab, hits, hr, outs),
    )


def _traded(db, factory):
    league = factory.league(state="season")
    season = factory.season(year=2025)
    factory.league_season(league, season)
    old, new = (
        factory.team(city="Old", mascot="Club"),
        factory.team(city="New", mascot="Club"),
    )
    for t in (old, new):
        factory.league_season_team(league, season, t)
    player = factory.rated_player(new, league, 60)
    _row(db, player, season, old, ab=200, hits=60, hr=8, outs=6)
    _row(db, player, season, new, ab=100, hits=30, hr=4, outs=6)
    return league, season, old, new, player


def test_leaders_get_one_row_with_his_totals_under_his_current_team(db_conn, factory):
    league, season, _, new, player = _traded(db_conn, factory)
    rows = PlayerSeasonStatsRepository(db_conn).get_batting_for_league(
        league.id, season.id
    )
    assert len(rows) == 1
    assert rows[0]["bat_ab"] == 300 and rows[0]["bat_home_runs"] == 12
    assert rows[0]["team_id"] == new.id and rows[0]["city"] == "New"


def test_pitching_leaders_need_9_outs_in_total(db_conn, factory):
    # 6 outs with each team: 12 in all, enough to show up.
    league, season, _, _, _ = _traded(db_conn, factory)
    rows = PlayerSeasonStatsRepository(db_conn).get_pitching_for_league(
        league.id, season.id
    )
    assert [r["pitch_outs"] for r in rows] == [12]


def test_his_player_card_shows_the_season_totals(db_conn, factory):
    _, season, _, _, player = _traded(db_conn, factory)
    row = PlayerSeasonStatsRepository(db_conn).get_player_season(player.id, season.id)
    assert row["bat_ab"] == 300 and row["bat_hits"] == 90


def test_roster_cards_show_the_season_totals(db_conn, factory):
    _, season, _, new, player = _traded(db_conn, factory)
    stats = PlayerSeasonStatsRepository(db_conn).get_team_stats_map(season.id, new.id)
    assert stats[player.id]["bat_ab"] == 300


def test_team_stats_keep_each_teams_share(db_conn, factory):
    _, season, old, new, player = _traded(db_conn, factory)
    repo = PlayerSeasonStatsRepository(db_conn)
    assert [r["bat_ab"] for r in repo.get_for_team(season.id, old.id)] == [200]
    assert [r["bat_ab"] for r in repo.get_for_team(season.id, new.id)] == [100]
