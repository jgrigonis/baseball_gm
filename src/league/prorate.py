# src/league/prorate.py
#
# Salaries split by days for players who change teams during the season
# (Josh, 2026-11-13). A team's payroll for a season is the full salary of
# everyone it holds (ContractRepository.payroll), so before this a team that
# traded a $20M player away at the deadline paid nothing of it, and a team
# that signed a free agent in September paid his whole year, luxury tax
# included. Now each in-season move leaves a pair of adjustments
# (payroll_adjustments) for the share of the season already played:
#
#   - a trade or waiver claim: the old team keeps that share of his salary
#     on its books (+), the new team doesn't carry it (-). Only guaranteed
#     deals: the rest aren't owed (a farm hand's deal costs nothing until he
#     plays on the 40-man, and then it's guaranteed).
#   - a free agent signed after Opening Day: the new team doesn't carry the
#     share already played (-), and a team still paying him from a release
#     only gets the rest of his new salary off its bill (+ that share of the
#     offset, src/db/repositories/contract_repo.py apply_offset).
#
# A player traded twice comes out right without anything special: each move
# hands the next team the share it didn't have him. The share of the season
# played is the regular-season games completed, league-wide. Moves outside
# the regular season and the playoffs (the offseason, the draft, the
# preseason) have nothing to split. The luxury tax, the tax shares and
# profit at season's end all read payroll, so they follow.

from __future__ import annotations

IN_SEASON = ("season", "playoffs")


def season_played(conn, league_id: str) -> float:
    """The share of the current regular season already played, 0 to 1. 0
    outside the regular season and the playoffs."""
    row = conn.execute(
        "SELECT state FROM leagues WHERE id = %s", (league_id,)
    ).fetchone()
    if not row or row["state"] not in IN_SEASON:
        return 0.0
    row = conn.execute(
        """SELECT COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE g.completed = 1) AS done
           FROM games g
           WHERE g.series_id IS NULL
             AND g.season_id = (
                 SELECT s.id FROM seasons s
                 JOIN league_seasons ls ON ls.season_id = s.id
                 WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1)""",
        (league_id,),
    ).fetchone()
    if not row or not row["total"]:
        return 0.0
    return row["done"] / row["total"]


def still_to_pay(conn, league_id: str) -> float:
    """The share of this season's salary a team taking on a player now
    still pays: what's left of the season."""
    return 1.0 - season_played(conn, league_id)


def _add(conn, league_id, team_id, year, player_id, amount, reason, played) -> None:
    amount = round(amount)
    if not team_id or not amount:
        return
    conn.execute(
        """INSERT INTO payroll_adjustments
               (league_id, team_id, year, player_id, amount, reason, played)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (league_id, team_id, year, player_id, amount, reason, played),
    )


def changed_teams(
    conn,
    league_id: str,
    player_id: str,
    from_team: str,
    to_team: str,
    salary: int,
    year: int,
    reason: str,
) -> None:
    """A guaranteed deal of this salary moved from one team to another (a
    trade, or a claim off waivers): the old team pays for the season played
    so far, the new one the rest."""
    played = season_played(conn, league_id)
    if not played or not salary:
        return
    _add(conn, league_id, from_team, year, player_id, salary * played, reason, played)
    _add(conn, league_id, to_team, year, player_id, -salary * played, reason, played)


def signed_mid_season(
    conn,
    league_id: str,
    player_id: str,
    team_id: str,
    salary: int,
    year: int,
    owed: list[tuple[str, int]] = (),
) -> None:
    """A free agent signed now for this salary: his new team pays only the
    rest of the season. owed is (team, salary) for each team still paying
    him from a release, whose bill his new salary only offsets from now on."""
    played = season_played(conn, league_id)
    if not played or not salary:
        return
    _add(conn, league_id, team_id, year, player_id, -salary * played, "signed", played)
    for old_team, old_salary in owed:
        offset = min(salary, old_salary)
        _add(
            conn,
            league_id,
            old_team,
            year,
            player_id,
            offset * played,
            "offset",
            played,
        )
