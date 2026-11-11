# src/api/services/owner_review.py
#
# The owner's end-of-season review (src/league/owner_scoring.py): when the
# playoffs end, each owner judges the season their GM just had, and the GM's
# job security moves. One gm_season_evaluations row per GM and season holds
# the verdict, each dimension's score, the facts it was judged on and the job
# security after it. Admins see all of it; GMs never see a number.
#
# A GM whose security falls past the line is stored as fired only when the
# league has owner firing on (leagues.owner_firing; never in Speed Blitz or a
# tutorial) and the owner's rules allow it (owner_scoring.judge: honeymoon,
# warning first). Otherwise they're warned, with would_fire in the detail, so
# the numbers can be tuned. src/api/services/firing.py carries firings out.
#
# Job security belongs to one GM under one owner. A person taking over a team,
# or an AI GM taking over from a person who left, starts at the owner's grace
# level. An owner only judges seasons from their first (team_owners.since_year).

from __future__ import annotations

from psycopg.types.json import Jsonb

from src.api.services import icons
from src.db.repositories.budget_repo import BudgetRepository
from src.api.services import owners as owner_service
from src.league import budget as bg
from src.league import finances as fn
from src.league import owner_scoring as sc
from src.league import owners
from src.league.league_modes import get_mode


def review_season(conn, league_id: str, season_id: str, year: int) -> dict[str, dict]:
    """Judge every team's season. Returns the stored rows by team id."""
    league = conn.execute(
        "SELECT mode, owner_firing, is_practice FROM leagues WHERE id = %s",
        (league_id,),
    ).fetchone()
    if not league:
        return {}
    money = get_mode(league["mode"]).budgets
    can_fire = firing_on(league)
    by_team = owner_service.ensure(conn, league_id)
    facts = gather(conn, league_id, season_id, year, by_team)
    gms = {
        r["team_id"]: dict(r)
        for r in conn.execute(
            """SELECT id, team_id, user_id, persona_id FROM gms
               WHERE league_id = %s AND team_id IS NOT NULL AND fired_at IS NULL
               ORDER BY is_ai""",  # a person's row first
            (league_id,),
        ).fetchall()
        if r["team_id"]
    }
    # Every owner's raw verdict first, so each can be graded on the
    # league's curve (owner_scoring.curved).
    judged, raw = {}, {}
    for team_id, owner in by_team.items():
        gm = gms.get(team_id)
        season = facts.get(team_id)
        if not gm or not season or year < owner["since_year"]:
            continue
        scores = sc.score_dimensions(season, owner["traits"], money)
        judged[team_id] = scores
        raw[team_id] = sc.season_score(scores, owner["weights"])
    curve = sc.curved(raw)
    out = {}
    for team_id, scores in judged.items():
        owner, gm, season = by_team[team_id], gms[team_id], facts[team_id]
        score = curve[team_id]
        who = gm["user_id"] or gm["persona_id"] or gm["id"]
        before, tenure = _tenure(conn, gm["id"], who, owner, year)
        rules = sc.firing_rules(owner.get("archetype"))
        after, verdict, would_fire = sc.judge(
            before, score, owner["traits"], season.champion, tenure, rules
        )
        if verdict == "fired" and not can_fire:
            verdict = "warned"
        detail = {
            "who": who,
            "scores": scores,
            "raw_score": round(raw[team_id], 4),
            "facts": season.as_dict(),
            "security_before": before,
            "would_fire": would_fire,
            "seasons_under_owner": tenure.seasons + 1,
            "win_target": round(
                sc.win_target(
                    season.rank_before, owners.clean_traits(owner["traits"])["ambition"]
                ),
                3,
            ),
        }
        games = season.wins + season.losses
        conn.execute(
            """INSERT INTO gm_season_evaluations
                   (gm_id, season_id, wins, losses, expected_wins, made_playoffs,
                    won_championship, verdict, owner_id, score, job_security,
                    detail)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (gm_id, season_id) DO UPDATE SET
                   wins = EXCLUDED.wins, losses = EXCLUDED.losses,
                   expected_wins = EXCLUDED.expected_wins,
                   made_playoffs = EXCLUDED.made_playoffs,
                   won_championship = EXCLUDED.won_championship,
                   verdict = EXCLUDED.verdict, owner_id = EXCLUDED.owner_id,
                   score = EXCLUDED.score, job_security = EXCLUDED.job_security,
                   detail = EXCLUDED.detail""",
            (
                gm["id"],
                season_id,
                season.wins,
                season.losses,
                round(detail["win_target"] * games, 1),
                season.made_playoffs,
                season.champion,
                verdict,
                owner["owner_id"],
                round(score, 4),
                after,
                Jsonb(detail),
            ),
        )
        out[team_id] = {
            "gm_id": gm["id"],
            "score": score,
            "job_security": after,
            "verdict": verdict,
        }
    return out


def firing_on(league: dict) -> bool:
    """Whether owners in this league can fire GMs: the league's toggle, and
    never in Speed Blitz (too short) or a tutorial."""
    return (
        bool(league.get("owner_firing"))
        and not league.get("is_practice")
        and get_mode(league["mode"]).budgets
    )


def _tenure(
    conn, gm_id: str, who: str, owner: dict, year: int
) -> tuple[int, sc.Tenure]:
    """Job security coming into the season, and what the owner remembers of
    this GM: the seasons this GM (the same person or AI persona) has had
    under this owner on this team, in a row, newest first. A new GM starts at
    the owner's grace level."""
    rows = conn.execute(
        """SELECT e.job_security, e.score, e.detail, e.owner_id
           FROM gm_season_evaluations e
           JOIN seasons s ON s.id = e.season_id
           WHERE e.gm_id = %s AND s.year < %s AND e.job_security IS NOT NULL
           ORDER BY s.year DESC""",
        (gm_id, year),
    ).fetchall()
    mine = []
    for r in rows:
        if r["owner_id"] != owner["owner_id"] or (r["detail"] or {}).get("who") != who:
            break
        mine.append(r)
    if not mine:
        grace = sc.grace(owners.clean_traits(owner["traits"])["patience"])
        return grace, sc.Tenure()
    last = mine[0]
    return last["job_security"], sc.Tenure(
        seasons=len(mine),
        last_score=last["score"],
        last_security=last["job_security"],
    )


def security_now(conn, league_id: str) -> dict[str, dict]:
    """Each team's GM's latest review, by team id, for the admin pages:
    score, job security, verdict and detail."""
    rows = conn.execute(
        """SELECT DISTINCT ON (g.team_id) g.team_id, e.score, e.job_security,
                  e.verdict, e.detail, s.year
           FROM gm_season_evaluations e
           JOIN gms g ON g.id = e.gm_id
           JOIN seasons s ON s.id = e.season_id
           WHERE g.league_id = %s AND g.fired_at IS NULL AND e.job_security IS NOT NULL
           ORDER BY g.team_id, s.year DESC""",
        (league_id,),
    ).fetchall()
    return {r["team_id"]: dict(r) for r in rows}


# ── Gathering the season ─────────────────────────────────────────────────────


def gather(
    conn, league_id: str, season_id: str, year: int, by_team: dict[str, dict]
) -> dict[str, sc.TeamSeason]:
    """Every team's season, as owners judge it."""
    record = {
        r["team_id"]: (int(r["w"] or 0), int(r["l"] or 0))
        for r in conn.execute(
            """SELECT tgs.team_id, SUM(tgs.win) AS w, SUM(tgs.loss) AS l
               FROM team_game_stats tgs JOIN games g ON g.id = tgs.game_id
               WHERE g.season_id = %s AND g.completed = 1 AND g.series_id IS NULL
               GROUP BY tgs.team_id""",
            (season_id,),
        ).fetchall()
    }
    first = _team_state(conn, league_id, season_id, "ASC")
    last = _team_state(conn, league_id, season_id, "DESC")
    playoffs = _playoffs(conn, season_id)
    money = {
        r["team_id"]: dict(r)
        for r in conn.execute(
            """SELECT team_id, cap, budget, payroll, revenue, playoff_revenue,
                      profit, fans_before, fans_after, attendance, crowd_games,
                      crowd_in_park, capacity
               FROM team_budgets WHERE league_id = %s AND year = %s""",
            (league_id, year),
        ).fetchall()
    }
    if any(m.get("crowd_games") is None for m in money.values()):
        # The season's still on: its crowds so far.
        live = BudgetRepository(conn).crowds(league_id, year)
        for team_id, m in money.items():
            c = live.get(team_id)
            if m.get("crowd_games") is None and c:
                m.update(
                    attendance=c["attendance"],
                    crowd_games=c["counted"],
                    crowd_in_park=c["in_park"],
                    capacity=c["capacity"],
                )
    par = _profit_par(money)
    homegrown = _homegrown(conn, league_id, list(by_team))
    all_stars = _count(
        conn,
        "SELECT team_id, COUNT(*) AS n FROM all_stars WHERE season_id = %s"
        " GROUP BY team_id",
        (season_id,),
    )
    awards = _count(
        conn,
        "SELECT team_id, COUNT(*) AS n FROM season_awards"
        " WHERE season_id = %s AND player_id IS NOT NULL AND team_id IS NOT NULL"
        " GROUP BY team_id",
        (season_id,),
    )
    trades = _count(
        conn,
        """SELECT team_id, COUNT(*) AS n FROM (
               SELECT from_team_id AS team_id FROM trade_offers
               WHERE season_id = %s AND status = 'accepted'
               UNION ALL
               SELECT to_team_id FROM trade_offers
               WHERE season_id = %s AND status = 'accepted') x
           GROUP BY team_id""",
        (season_id, season_id),
    )
    lost_icons = _icons_lost(conn, league_id, season_id, year)
    good_releases = _good_releases(conn, league_id, year)
    teams = list(by_team)
    share = {t: mine / n if n else 0.0 for t, (mine, n) in homegrown.items()}
    league_home = sum(share.get(t, 0.0) for t in teams) / max(1, len(teams))
    league_stars = sum(
        all_stars.get(t, 0) + 1.5 * awards.get(t, 0) for t in teams
    ) / max(1, len(teams))
    out = {}
    for team_id, owner in by_team.items():
        w, l = record.get(team_id, (0, 0))
        m = money.get(team_id, {})
        p = playoffs.get(team_id, {})
        rival = owner.get("rival_team_id")
        rw, rl = _vs(conn, season_id, team_id, rival) if rival else (0, 0)
        revenue = (
            (m.get("revenue") or 0) + (m.get("playoff_revenue") or 0)
            if m.get("revenue") is not None
            else None
        )
        out[team_id] = sc.TeamSeason(
            wins=w,
            losses=l,
            rank_before=first.get(team_id, {}).get("rank_now", 0.5),
            rank_future=last.get(team_id, {}).get("rank_future", 0.5),
            farm_rank=last.get(team_id, {}).get("farm_rank", 0.5),
            made_playoffs=bool(p),
            rounds_won=p.get("rounds_won", 0),
            champion=p.get("champion", False),
            payroll=m.get("payroll"),
            budget=m.get("budget"),
            revenue=revenue,
            profit=m.get("profit"),
            profit_par=par.get(team_id),
            fans_before=m.get("fans_before"),
            fans_after=m.get("fans_after"),
            crowd_score=_crowd_score(m),
            homegrown_share=share.get(team_id, 0.0),
            homegrown_players=homegrown.get(team_id, (0, 0))[0],
            roster_players=homegrown.get(team_id, (0, 0))[1],
            league_homegrown=league_home,
            league_star_points=league_stars,
            all_stars=all_stars.get(team_id, 0),
            award_winners=awards.get(team_id, 0),
            icons_lost=lost_icons.get(team_id, 0),
            trades=trades.get(team_id, 0),
            releases=good_releases.get(team_id, 0),
            rival_wins=rw,
            rival_losses=rl,
        )
    return out


# A season needs this many home crowds to be judged on them (a league that
# picked crowds up mid-season reads fan interest, as before).
CROWD_GAMES_TO_JUDGE = 20


def _crowd_score(m: dict) -> float | None:
    games = m.get("crowd_games") or 0
    if games < CROWD_GAMES_TO_JUDGE or not m.get("capacity"):
        return None
    return fn.attendance_score(
        m["attendance"] / games, (m["crowd_in_park"] or 0) / games, m["capacity"]
    )


def _profit_par(money: dict[str, dict]) -> dict[str, int]:
    """Each team's par profit: its regular-season revenue less what a middle
    owner (Spending 50) would pay under the league's cap, the tax on it and
    fixed costs (src/league/budget.py, src/league/finances.py)."""
    revenues = [m["revenue"] for m in money.values() if m.get("revenue")]
    if not revenues:
        return {}
    costs = fn.fixed_costs(sum(revenues) / len(revenues))
    out = {}
    for team_id, m in money.items():
        if not m.get("revenue") or not m.get("cap"):
            continue
        payroll = bg.owner_budget(m["cap"], 50)
        tax = bg.luxury_tax(payroll, m["cap"])
        out[team_id] = fn.profit(m["revenue"], payroll, tax, costs)
    return out


def _count(conn, sql: str, params: tuple) -> dict[str, int]:
    return {r["team_id"]: int(r["n"]) for r in conn.execute(sql, params).fetchall()}


def _team_state(conn, league_id: str, season_id: str, order: str) -> dict[str, dict]:
    """Each team's first (ASC) or last (DESC) team-state inputs this season."""
    rows = conn.execute(
        f"""SELECT DISTINCT ON (team_id) team_id, inputs FROM team_states
            WHERE league_id = %s AND season_id = %s
            ORDER BY team_id, id {order}""",
        (league_id, season_id),
    ).fetchall()
    return {r["team_id"]: r["inputs"] or {} for r in rows}


def _playoffs(conn, season_id: str) -> dict[str, dict]:
    """Teams in the playoffs, by team id: series won, and the champion. The
    playoffs are over when owners judge, so each series' winner is the team
    that won more of its games."""
    series: dict[str, dict] = {}
    for r in conn.execute(
        """SELECT g.series_id, s.name, g.home_team_id, g.away_team_id, g.winner_id
           FROM games g JOIN series s ON s.id = g.series_id
           WHERE s.season_id = %s AND g.completed = 1""",
        (season_id,),
    ).fetchall():
        one = series.setdefault(r["series_id"], {"name": r["name"], "wins": {}})
        for t in (r["home_team_id"], r["away_team_id"]):
            one["wins"].setdefault(t, 0)
        if r["winner_id"]:
            one["wins"][r["winner_id"]] = one["wins"].get(r["winner_id"], 0) + 1
    out: dict[str, dict] = {}
    for one in series.values():
        for t in one["wins"]:
            out.setdefault(t, {"rounds_won": 0, "champion": False})
        winner = max(one["wins"], key=lambda t: one["wins"][t])
        out[winner]["rounds_won"] += 1
        if one["name"] == "Finals":
            out[winner]["champion"] = True
    return out


def _homegrown(conn, league_id: str, team_ids: list[str]) -> dict[str, float]:
    """How many players on each team's 40-man roster it drafted itself, and
    how many players are on it."""
    rows = conn.execute(
        """SELECT tp.team_id,
                  COUNT(*) AS n,
                  COUNT(*) FILTER (WHERE EXISTS (
                      SELECT 1 FROM draft_picks dp JOIN drafts d ON d.id = dp.draft_id
                      WHERE d.league_id = %s AND dp.player_id = tp.player_id
                        AND dp.team_id = tp.team_id)) AS mine
           FROM team_players tp
           JOIN player_status ps ON ps.player_id = tp.player_id
           WHERE tp.team_id = ANY(%s) AND ps.status IN ('26man', '40man')
           GROUP BY tp.team_id""",
        (league_id, team_ids),
    ).fetchall()
    return {r["team_id"]: (r["mine"], r["n"]) for r in rows}


def _icons_lost(conn, league_id: str, season_id: str, year: int) -> dict[str, int]:
    """The franchise icons (src/api/services/icons.py) each team traded away
    or released this season."""
    rows = conn.execute(
        """SELECT DISTINCT team_id, player_id FROM (
               SELECT i.from_team_id AS team_id, i.player_id
               FROM trade_offer_items i JOIN trade_offers o ON o.id = i.offer_id
               WHERE o.season_id = %s AND o.status = 'accepted'
               UNION ALL
               SELECT c.released_team_id, c.player_id FROM player_contracts c
               JOIN players p ON p.id = c.player_id
               WHERE p.league_id = %s AND c.released_year = %s
                 AND c.released_team_id IS NOT NULL
           ) gone""",
        (season_id, league_id, year),
    ).fetchall()
    out: dict[str, int] = {}
    for _, team_id in icons.find(conn, [(r["player_id"], r["team_id"]) for r in rows]):
        out[team_id] = out.get(team_id, 0) + 1
    return out


def _good_releases(conn, league_id: str, year: int) -> dict[str, int]:
    """How many players each team released this season who were B- or
    better (graded now): roster turnover, like trades."""
    from src.api.grade_curves import GRADES
    from src.api.services.news.moves import is_notable

    rows = conn.execute(
        """SELECT DISTINCT c.released_team_id AS team_id, c.player_id
           FROM player_contracts c
           WHERE c.league_id = %s AND c.released_year = %s
             AND c.released_team_id IS NOT NULL""",
        (league_id, year),
    ).fetchall()
    grades = icons._grades(conn, list({r["player_id"] for r in rows}))
    out: dict[str, int] = {}
    for r in rows:
        g = grades.get(r["player_id"])
        if g in GRADES and is_notable(g):
            out[r["team_id"]] = out.get(r["team_id"], 0) + 1
    return out


def _vs(conn, season_id: str, team_id: str, rival_id: str) -> tuple[int, int]:
    """A team's regular-season record against its owner's rival."""
    row = conn.execute(
        """SELECT COUNT(*) FILTER (WHERE winner_id = %s) AS w,
                  COUNT(*) FILTER (WHERE winner_id = %s) AS l
           FROM games
           WHERE season_id = %s AND completed = 1 AND series_id IS NULL
             AND ((home_team_id = %s AND away_team_id = %s)
               OR (home_team_id = %s AND away_team_id = %s))""",
        (team_id, rival_id, season_id, team_id, rival_id, rival_id, team_id),
    ).fetchone()
    return int(row["w"] or 0), int(row["l"] or 0)
