# src/api/view_models/standings.py
#
# Context for the standings tab: the ranked table plus the GM's upcoming and
# recent games and injury report.

from __future__ import annotations

from src.api.services import owners, sim_summary
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.standings_repo import StandingsRepository
from src.db.repositories.team_state_repo import TeamStateRepository
from src.league import divisions, money_state, team_state


def calc_streak(results: list) -> str:
    """results[0] is most recent game"""
    if not results:
        return "—"
    letter = "W" if results[0] else "L"
    count = 0
    for r in results:
        if bool(r) == (letter == "W"):
            count += 1
        else:
            break
    return f"{letter}{count}"


def standings_rows(
    db, league_id: str, season_id: str, my_team_id: str | None
) -> list[dict]:
    """The ranked standings table for one season, best record first."""
    gm_repo = GMRepository(db)
    st_repo = StandingsRepository(db)
    ra_map = st_repo.get_runs_allowed(season_id)
    ha_map = st_repo.get_home_away_splits(season_id)
    human_team_ids = gm_repo.get_human_team_ids(league_id)
    recent_rows = st_repo.get_recent_results(season_id)
    # Each front office's latest read on its team (src/league/team_state.py).
    states = TeamStateRepository(db).latest(league_id, season_id)
    # And where it stands with its owner's money (src/league/money_state.py),
    # this season only: the books are now, not then.
    # A person's team shows its payroll and spending against the cap and
    # its owner instead (money_state.payroll_state).
    current = season_id == SeasonRepository(db).get_current_id_for_league(league_id)
    money = owners.season_money_states(db, league_id, season_id) if current else {}
    money_tags: dict[str, tuple[str, str, str]] = {
        t: (m, money_state.label(m), money_state.TIPS.get(m, ""))
        for t, m in money.items()
    }
    if money:
        year = SeasonRepository(db).get_year(season_id)["year"]
        budgets = BudgetRepository(db)
        for t in human_team_ids:
            standing = budgets.standing(league_id, t, year)
            m = money_state.payroll_state(standing)
            if m:
                money_tags[t] = (
                    m,
                    money_state.PAYROLL_LABELS[m],
                    money_state.payroll_tip(m, standing),
                )
    gms = team_gms(db, league_id)

    # Build per-team recent results
    team_recent: dict[str, list] = {}
    for r in recent_rows:
        tid = r["team_id"]
        if tid not in team_recent:
            team_recent[tid] = []
        if len(team_recent[tid]) < 10:
            team_recent[tid].append(r["win"])

    # Sort by win pct descending, with H2H and RS tiebreakers
    rows = st_repo.get_records(league_id, season_id)
    raw_rows = [
        {
            **r,
            "win_pct": (
                r["wins"] / (r["wins"] + r["losses"])
                if (r["wins"] + r["losses"])
                else 0.0
            ),
        }
        for r in rows
    ]
    ranked = st_repo.sort(season_id, raw_rows)
    leader_wins = ranked[0]["wins"] or 0 if ranked else 0
    leader_losses = ranked[0]["losses"] or 0 if ranked else 0

    teams = []
    for rank, r in enumerate(ranked, 1):
        wins = r["wins"] or 0
        losses = r["losses"] or 0
        played = wins + losses
        pct = wins / played if played else 0.0
        gb_val = ((leader_wins - wins) + (losses - leader_losses)) / 2
        gb = (
            "—"
            if rank == 1
            else (f"{gb_val:.1f}" if gb_val != int(gb_val) else str(int(gb_val)))
        )
        recent = team_recent.get(r["team_id"], [])
        rs = r["runs_scored"] or 0
        ra = ra_map.get(r["team_id"], 0)
        ha = ha_map.get(r["team_id"], {"hw": 0, "hl": 0, "aw": 0, "al": 0})
        l10_wins = sum(1 for w in recent[:10] if w)
        l10_losses = 10 - l10_wins if len(recent) >= 10 else len(recent) - l10_wins
        pct_str = f"{pct:.3f}"
        pct_str = pct_str[1:] if pct_str.startswith("0") else pct_str
        teams.append(
            {
                "rank": rank,
                "team_id": r["team_id"],
                "city": r["city"],
                "mascot": r["mascot"],
                "wins": wins,
                "losses": losses,
                "pct": pct_str,
                "gb": gb,
                "streak": calc_streak(recent),
                "home": f"{ha['hw']}-{ha['hl']}",
                "away": f"{ha['aw']}-{ha['al']}",
                "l10": f"{l10_wins}-{l10_losses}",
                "rs": rs,
                "ra": ra,
                "is_human": r["team_id"] in human_team_ids,
                "state": states.get(r["team_id"], {}).get("state"),
                "state_label": team_state.LABELS.get(
                    states.get(r["team_id"], {}).get("state"), ""
                ),
                "money": money_tags.get(r["team_id"], (None, "", ""))[0],
                "money_label": money_tags.get(r["team_id"], (None, "", ""))[1],
                "money_tip": money_tags.get(r["team_id"], (None, "", ""))[2],
                "is_mine": r["team_id"] == my_team_id,
                "gm": gms.get(r["team_id"]),
            }
        )
    return teams


def _games_behind(leader: dict, team: dict) -> str:
    gb = ((leader["wins"] - team["wins"]) + (team["losses"] - leader["losses"])) / 2
    if team is leader:
        return "—"
    return f"{gb:.1f}" if gb != int(gb) else str(int(gb))


def division_groups(db, league_id: str, teams: list[dict]) -> list[dict]:
    """The standings split by league and division: [{name, divisions:
    [{name, teams}]}], each division best first with games behind its
    leader. Empty for a league without divisions."""
    by_id = {t["team_id"]: t for t in teams}
    out = []
    for conf in divisions.load(db, league_id):
        divs = []
        for div in conf.divisions:
            rows = sorted(
                (by_id[t] for t in div.team_ids if t in by_id),
                key=lambda t: t["rank"],
            )
            rows = [
                {**t, "rank": i, "gb": _games_behind(rows[0], t)}
                for i, t in enumerate(rows, 1)
            ]
            divs.append({"name": div.name, "teams": rows})
        out.append({"name": conf.name, "divisions": divs})
    return out


def team_gms(db, league_id: str) -> dict[str, dict]:
    """Who runs each team now ({name, persona_id, username}), the person if
    there is one."""
    rows = db.execute(
        """SELECT g.team_id, g.display_name AS name, g.persona_id, u.username
           FROM gms g LEFT JOIN users u ON u.id = g.user_id
           WHERE g.league_id = %s AND g.team_id IS NOT NULL AND g.fired_at IS NULL
           ORDER BY g.is_ai DESC""",
        (league_id,),
    ).fetchall()
    # People come last, so theirs wins.
    return {r["team_id"]: dict(r) for r in rows}


def standings_context(
    db,
    league_id: str,
    season_id: str | None,
    my_team_id: str | None,
    past_season: bool = False,
) -> dict:
    """`past_season` drops the GM's upcoming games and injury report, which
    only make sense for the season being played."""
    teams = []
    upcoming = []
    recent_games = []
    injuries = []

    if season_id:
        game_repo = GameRepository(db)
        inj_repo = InjuryRepository(db, league_id)
        teams = standings_rows(db, league_id, season_id, my_team_id)
        # x / y / e: clinched a spot, clinched the division, eliminated.
        marks = sim_summary.clinch_marks(db, league_id, season_id, teams)
        for t in teams:
            t["clinch"] = marks.get(t["team_id"])

        # ── My next 5 upcoming games ──────────────────────────────────────────
        upcoming = []
        if my_team_id and not past_season:
            for g_row in game_repo.get_team_upcoming(season_id, my_team_id, limit=5):
                is_home = g_row["home_team_id"] == my_team_id
                opp_city = g_row["away_city"] if is_home else g_row["home_city"]
                opp_mascot = g_row["away_mascot"] if is_home else g_row["home_mascot"]
                upcoming.append(
                    {
                        "date": g_row["game_date"],
                        "opp_id": g_row["away_team_id"]
                        if is_home
                        else g_row["home_team_id"],
                        "home_away": "vs" if is_home else "@",
                        "opponent": f"{opp_city} {opp_mascot}",
                    }
                )

        # ── My last 5 completed games ─────────────────────────────────────────
        recent_games = []
        if my_team_id:
            for g_row in game_repo.get_team_results(season_id, my_team_id, limit=5):
                is_home = g_row["home_team_id"] == my_team_id
                my_score = g_row["home_score"] if is_home else g_row["away_score"]
                opp_score = g_row["away_score"] if is_home else g_row["home_score"]
                opp_city = g_row["away_city"] if is_home else g_row["home_city"]
                opp_mascot = g_row["away_mascot"] if is_home else g_row["home_mascot"]
                won = (my_score or 0) > (opp_score or 0)
                recent_games.append(
                    {
                        "game_id": g_row["game_id"],
                        "date": g_row["game_date"],
                        "home_away": "vs" if is_home else "@",
                        "opponent": f"{opp_city} {opp_mascot}",
                        "my_score": my_score,
                        "opp_score": opp_score,
                        "result": "W" if won else "L",
                    }
                )

        # ── Injury report ─────────────────────────────────────────────────────
        injuries = []
        if my_team_id and not past_season:
            injuries = inj_repo.get_team_injury_report(my_team_id, league_id)

    mine = next((t for t in teams if t["team_id"] == my_team_id), None)
    return {
        "teams": teams,
        "groups": division_groups(db, league_id, teams) if teams else [],
        # "The front office sees a team that's ramping up."
        "my_state": team_state.describe(mine["state"])
        if mine and mine["state"]
        else "",
        "games_played": (
            sum(t["wins"] + t["losses"] for t in teams) // 2 if teams else 0
        ),
        "upcoming": upcoming,
        "recent_games": recent_games,
        "injuries": injuries,
        "my_team_id": my_team_id,
    }
