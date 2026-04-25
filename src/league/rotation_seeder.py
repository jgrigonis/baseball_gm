# src/league/rotation_seeder.py
from src.db.repositories.bullpen_roles_repo import BullpenRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.team_rotations_repo import TeamRotationsRepository
from src.player.player_evaluator import PlayerEvaluator


def seed_ai_rotations(
    conn,
    season_id: str,
    ai_team_ids: set[str],
    statuses: list[str],
    effective_date: str,
) -> int:
    """
    Seed starting rotations and bullpen roles for AI-managed teams.

    Loads players fresh from DB by team+status so the result always reflects
    the current roster, not a stale in-memory team object. Human teams must be
    excluded by the caller via ai_team_ids.

    Args:
        conn:           DB connection
        season_id:      Season to write rotation rows into
        ai_team_ids:    Team IDs to process (caller excludes human teams)
        statuses:       Roster statuses to consider, e.g. ["26man", "40man"]
                        for blitz or ["26man"] for longform
        effective_date: Sim-world date string for rotation entries — never
                        pass a real-world date here

    Returns:
        Number of teams seeded
    """
    if not ai_team_ids:
        return 0

    status_repo = PlayerStatusRepository(conn)
    player_repo = PlayerRepository(conn)
    rot_repo = TeamRotationsRepository(conn)
    bp_repo = BullpenRepository(conn)
    team_repo = TeamRepository(conn)

    teams = team_repo.get_teams_by_season(season_id)
    seeded = 0

    for team in teams:
        if team.id not in ai_team_ids:
            continue

        # Load active player IDs directly from DB — never use team.players
        active_ids: set[str] = set()
        for status in statuses:
            active_ids.update(status_repo.get_by_team_and_status(team.id, status))

        players = [p for pid in active_ids if (p := player_repo.look_up(pid))]

        pitchers = [p for p in players if p.is_pitcher()]
        pitchers.sort(
            key=lambda p: PlayerEvaluator.rate_player(p.skills).get("sp", 0),
            reverse=True,
        )
        rotation = [p.id for p in pitchers[:5]]
        if not rotation:
            print(f"  Warning: No pitchers found for AI team {team.name}, skipping rotation.")
            continue

        rot_repo.replace_rotation(
            team_id=team.id,
            season_id=season_id,
            player_ids=rotation,
            effective_date=effective_date,
            next_order=1,
        )

        rotation_set = set(rotation)
        relievers = [p for p in pitchers if p.id not in rotation_set]
        roles = team.set_bullpen_roles(rotation, relievers=relievers)
        if roles:
            bp_repo.set_roles(team.id, season_id, roles, effective_date)

        seeded += 1

    return seeded
