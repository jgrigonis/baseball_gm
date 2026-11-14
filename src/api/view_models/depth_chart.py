# src/api/view_models/depth_chart.py
"""
The depth chart (Josh, 2026-11-14): a team's rotation, bullpen, defense and
best bats, each with its grade and place in the league, plus who's next.

The Depth Chart tab shows it on a diamond (depth_chart.html).

- Group grades and places use the same team strength as the Power Rankings
  and the welcome screen's scouting report (power_rankings.team_strength), so
  the numbers agree everywhere.
- It follows the team's own choices so it matches the Lineup tab (Josh,
  2026-11-14): the starting 8 and batting order are a person's saved lineup
  vs RHP, else the lineup the team used in its last game, else
  power_rankings.starting_nine; the rotation is the saved rotation in order;
  the bullpen goes by its roles (Closer, Setup, Middle...). Only a team with
  nothing set falls back to ratings.
- Backups come from the whole organization, minor leaguers tagged: the next
  BACKUPS players at each fielding spot rated BACKUP_FLOOR or better there.
"""

from __future__ import annotations

from src.api.grade_curves import GRADES, overall_to_grade, role_to_grade
from src.api.view_models.welcome import ordinal
from src.db.repositories.draft_repo import DraftRepository
from src.league.offseason.draft_strategy import ratings, staff_groups
from src.league.power_rankings import starting_nine, team_strength

MAJORS = ("26man", "40man")
FIELD = ("c", "1b", "2b", "3b", "ss", "lf", "cf", "rf")
ROTATION = 5
RELIEVERS = 5  # besides the closer
NEXT_STARTERS = 2
NEXT_RELIEVERS = 1
BACKUPS = 2
BENCH_BATS = 3
BEST_BATS = 9
BACKUP_FLOOR = "C-"  # a backup rated worse than this isn't one
WEAK_BELOW = "C-"  # a starter graded worse than this is marked
WEAK_SHARE = 0.25  # bottom quarter of the league: the group is marked

GROUPS = (
    ("rotation", "Rotation", "rotation", "team_rotation"),
    ("bullpen", "Bullpen", "bullpen", "team_bullpen"),
    ("defense", "Defense", "defense", "team_defense"),
    ("bats", "Batting order", "hitting", "team_lineup"),
)


def _worse(grade: str, cut: str) -> bool:
    return grade in GRADES and GRADES.index(grade) > GRADES.index(cut)


def _teams(db, league_id: str, season_id: str) -> list[dict]:
    return [
        dict(r)
        for r in db.execute(
            """SELECT t.id, t.city, t.mascot
               FROM league_season_teams lst JOIN teams t ON t.id = lst.team_id
               WHERE lst.league_id = %s AND lst.season_id = %s
               ORDER BY t.city, t.mascot""",
            (league_id, season_id),
        ).fetchall()
    ]


ROLE_ORDER = ("Closer", "Setup", "Middle", "Long", "Specialist", "Utility")


def _roles(db, team_id: str, season_id: str) -> dict[str, str]:
    """{player_id: role} for the team's bullpen right now."""
    rows = db.execute(
        """SELECT player_id, role FROM bullpen_roles
           WHERE team_id = %s AND season_id = %s AND end_date IS NULL""",
        (team_id, season_id),
    ).fetchall()
    return {r["player_id"]: r["role"] for r in rows}


def _rotation_ids(db, team_id: str, season_id: str) -> list[str]:
    rows = db.execute(
        """SELECT player_id FROM team_rotations
           WHERE team_id = %s AND season_id = %s AND end_date IS NULL
           ORDER BY rotation_order""",
        (team_id, season_id),
    ).fetchall()
    return [r["player_id"] for r in rows]


def _lineup(db, league_id: str, team_id: str, season_id: str) -> list[tuple[str, str]]:
    """[(player_id, position)] in batting order: a person's saved lineup vs
    RHP (else their vs LHP one), else the lineup in the team's last game this
    season, else []."""
    from src.db.repositories.lineup_preference_repo import LineupPreferenceRepository

    saved = LineupPreferenceRepository(db).get_preferences(team_id, league_id, "R")
    rows = [r for r in saved or [] if r.get("batting_order")]
    if rows:
        return [(r["player_id"], (r["position"] or "").lower()) for r in rows]
    rows = db.execute(
        """SELECT s.player_id, s.position FROM game_lineup_slots s
           WHERE s.team_id = %s AND s.batting_order IS NOT NULL
             AND s.game_id = (
                 SELECT g.id FROM games g JOIN game_lineup_slots x ON x.game_id = g.id
                 WHERE g.season_id = %s AND x.team_id = %s
                 ORDER BY g.game_date DESC, g.id DESC LIMIT 1)
           ORDER BY s.batting_order""",
        (team_id, season_id, team_id),
    ).fetchall()
    return [(r["player_id"], (r["position"] or "").lower()) for r in rows]


def _entry(p, r, status, role, slot="") -> dict:
    grade = role_to_grade(r[role], role)
    return {
        "id": p.id,
        "name": f"{p.first_name} {p.last_name}".strip(),
        "last": p.last_name or p.first_name,
        "grade": grade,
        "slot": slot,
        "minors": status not in MAJORS,
        "weak": _worse(grade, WEAK_BELOW),
    }


def depth_chart(db, league_id: str, season_id: str | None, team_id: str) -> dict | None:
    """Everything both views show for `team_id`, or None if it isn't in the
    league this season."""
    if not season_id:
        return None
    teams = _teams(db, league_id, season_id)
    ids = [t["id"] for t in teams]
    if team_id not in ids:
        return None
    repo = DraftRepository(db)
    rosters = repo.get_roster_records(ids)
    staff = repo.get_staff_groups(ids)

    strength: dict[str, dict[str, float]] = {}
    mine_rated: list[tuple] = []
    for tid in ids:
        players = rosters.get(tid, [])
        if tid == team_id:
            mine_rated = [(p, ratings(p), status) for p, status in players]
            majors = [(p, r) for p, r, status in mine_rated if status in MAJORS]
        else:
            majors = [(p, ratings(p)) for p, status in players if status in MAJORS]
        groups = staff_groups([x for x in majors if x[0].is_pitcher()], staff)
        strength[tid] = team_strength(majors, groups)

    n = len(ids)
    groups_out = {}
    for key, label, area, kind in GROUPS:
        value = strength[team_id][area]
        rank = 1 + sum(1 for s in strength.values() if s[area] > value)
        groups_out[key] = {
            "label": label,
            "grade": overall_to_grade(value, kind),
            "rank": rank,
            "rank_text": f"{ordinal(rank)} of {n}",
            "weak": n >= 4 and rank > n * (1 - WEAK_SHARE),
        }

    majors = [(p, r, s) for p, r, s in mine_rated if s in MAJORS]
    pitchers = [x for x in majors if x[0].is_pitcher()]
    hitters = [x for x in majors if not x[0].is_pitcher()]
    by_id = {p.id: (p, r, s) for p, r, s in mine_rated}
    pgroups = staff_groups([(p, r) for p, r, _ in pitchers], staff)

    # Rotation: the saved rotation in order, else the top starters on the
    # staff; then the best arms behind them.
    on_team = {x[0].id: x for x in pitchers}
    sps = [
        on_team[pid] for pid in _rotation_ids(db, team_id, season_id) if pid in on_team
    ]
    if not sps:
        sps = sorted(
            (x for x in pitchers if pgroups.get(x[0].id) == "sp"),
            key=lambda x: x[1]["sp"],
            reverse=True,
        )[:ROTATION]
    rotation = [_entry(p, r, s, "sp", f"SP{i}") for i, (p, r, s) in enumerate(sps, 1)]
    used = {e["id"] for e in rotation}
    org_pitchers = [x for x in mine_rated if x[0].is_pitcher()]
    next_sp = [
        _entry(p, r, s, "sp")
        for p, r, s in sorted(
            (
                x
                for x in org_pitchers
                if x[0].id not in used and pgroups.get(x[0].id) != "rp"
            ),
            key=lambda x: x[1]["sp"],
            reverse=True,
        )[:NEXT_STARTERS]
    ]

    # Bullpen: the closer, then the best relievers.
    # By role when the bullpen has them (Closer, Setup, Middle...), best
    # first within a role; else by RP rating.
    roles = _roles(db, team_id, season_id)
    in_rot = {x[0].id for x in sps}
    rps = sorted(
        (
            x
            for x in pitchers
            if x[0].id not in in_rot
            and (x[0].id in roles if roles else pgroups.get(x[0].id) == "rp")
        ),
        key=lambda x: (
            ROLE_ORDER.index(roles[x[0].id]) if roles.get(x[0].id) in ROLE_ORDER else 9,
            -x[1]["rp"],
        ),
    )
    closer = next((x for x in rps if roles.get(x[0].id) == "Closer"), None)
    if closer is None and not roles and rps:
        closer = max(rps, key=lambda x: x[1]["cp"])
    bullpen = []
    if closer:
        bullpen.append(_entry(*closer, "cp", "CL"))
    rest = [x for x in rps if not closer or x[0].id != closer[0].id]
    short = {"Setup": "SU", "Middle": "MR", "Long": "LR", "Specialist": "SPC"}
    bullpen += [
        _entry(p, r, s, "rp", short.get(roles.get(p.id), "RP"))
        for p, r, s in rest[:RELIEVERS]
    ]
    if closer and rest:
        bullpen[0]["backups"] = [_entry(*rest[0], "cp")]
    shown = used | {e["id"] for e in bullpen}
    next_rp = [
        _entry(p, r, s, "rp")
        for p, r, s in sorted(
            (x for x in org_pitchers if x[0].id not in shown),
            key=lambda x: x[1]["rp"],
            reverse=True,
        )[:NEXT_RELIEVERS]
    ]

    # Defense: the starting 8 and who's next at each spot.
    hitter_ids = {x[0].id for x in hitters}
    order = [
        (pid, pos)
        for pid, pos in _lineup(db, league_id, team_id, season_id)
        if pid in hitter_ids
    ]
    if len(order) >= 8:
        nine = [(by_id[pid][0], pos) for pid, pos in order]
    else:
        order = []
        nine = starting_nine([(p, r) for p, r, _ in hitters])
    starters = {pos: p.id for p, pos in nine}
    in_nine = set(starters.values())
    org_hitters = [x for x in mine_rated if not x[0].is_pitcher()]
    defense = []
    for pos in FIELD:
        pid = starters.get(pos)
        e = (
            _entry(*by_id[pid], pos, pos.upper())
            if pid
            else {"slot": pos.upper(), "name": None, "grade": "F", "weak": True}
        )
        e["spot"] = pos
        e["backups"] = [
            b
            for b in (
                _entry(p, r, s, pos)
                for p, r, s in sorted(
                    (x for x in org_hitters if x[0].id not in in_nine),
                    key=lambda x: x[1][pos],
                    reverse=True,
                )
            )
            if not _worse(b["grade"], BACKUP_FLOOR)
        ][:BACKUPS]
        defense.append(e)
    dh = next(
        (
            _entry(*by_id[p.id], "overall_offense", "DH")
            for p, pos in nine
            if pos == "dh"
        ),
        None,
    )

    # Bats: the batting order (else the best 9 by Overall Offense), then
    # the best of the bench.
    by_bat = sorted(hitters, key=lambda x: x[1]["overall_offense"], reverse=True)
    lineup_ids = [pid for pid, _ in order] or [x[0].id for x in by_bat[:BEST_BATS]]
    bats = []
    for i, pid in enumerate(lineup_ids, 1):
        e = _entry(*by_id[pid], "overall_offense", str(i))
        e["pos"] = next((pos.upper() for q, pos in nine if q.id == pid), "")
        bats.append(e)
    bench = [
        _entry(p, r, s, "overall_offense")
        for p, r, s in by_bat
        if p.id not in lineup_ids
    ][:BENCH_BATS]
    if not order:
        groups_out["bats"]["label"] = "Best 9 bats"

    team = next(t for t in teams if t["id"] == team_id)
    return {
        "team": team,
        "teams": teams,
        "groups": groups_out,
        "rotation": rotation,
        "next_starters": next_sp,
        "bullpen": bullpen,
        "next_relievers": next_rp,
        "defense": defense,
        "dh": dh,
        "bats": bats,
        "bench": bench,
        "from_lineup": bool(order),
    }
