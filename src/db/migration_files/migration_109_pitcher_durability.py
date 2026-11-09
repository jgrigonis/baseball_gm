"""
Pitchers get a real durability rating (Josh, 2026-11-09). Pitchers used to be
generated with durability around 10, like a hitting skill, so the game never
used it for them. Now it sets their injury risk like everyone else's, and new
pitchers are generated around 50.

Every existing pitcher's durability is re-rolled the way a new pitcher's is,
keeping whatever he has gained or lost since (aging) on top. His talent cap
gets the same room to grow a new player's has, and his skill history moves
with him so his career page doesn't jump. Custom-team pitchers someone edited
by hand get the real season's new value, unless they set it above the old
range themselves.
"""

import hashlib
import random

from psycopg.types.json import Jsonb

from src.player.player_skills import GENERATION_ADJUST, PlayerSkills
from src.player.positions import PITCHER_POSITIONS, SKILLS
from src.player.talent_caps import TALENT_SIGMA, expected_growth

VERSION = 109

# Old generation mean for pitchers (template 10 + GENERATION_ADJUST).
OLD_MEAN = 11.5
# Edited custom-team values at or under this were the old real values.
OLD_MAX = 30


def _rng(player_id: str) -> random.Random:
    seed = int(hashlib.sha1(f"{player_id}:durability".encode()).hexdigest()[:8], 16)
    return random.Random(seed)


def new_durability(player_id: str, old: int, old_cap: int | None):
    """(durability, talent cap) for a pitcher whose durability was `old`."""
    rng = _rng(player_id)
    mean = SKILLS["durability"] + GENERATION_ADJUST["durability"]
    base = PlayerSkills.generate_stat(rng, mean=round(mean))
    value = max(1, min(100, base + round(old - OLD_MEAN)))
    growth = max(
        0.0, rng.gauss(expected_growth(base, "durability"), TALENT_SIGMA["durability"])
    )
    cap = min(100, base + round(growth))
    # A veteran past his peak already used his growth: never below where he is.
    cap = max(cap, value)
    if old_cap is None:
        cap = None
    return value, cap


def upgrade(conn):
    rows = conn.execute(
        """SELECT p.id, ps.durability, tc.durability AS cap
           FROM players p
           JOIN player_skills ps ON ps.player_id = p.id
           LEFT JOIN player_talent_caps tc ON tc.player_id = p.id
           WHERE p.position = ANY(%s)""",
        (list(PITCHER_POSITIONS),),
    ).fetchall()
    skills, caps, history = [], [], []
    for r in rows:
        value, cap = new_durability(r["id"], r["durability"], r["cap"])
        skills.append((value, r["id"]))
        history.append((value - r["durability"], r["id"]))
        if cap is not None:
            caps.append((cap, r["id"]))
    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE player_skills SET durability = %s WHERE player_id = %s", skills
        )
        cur.executemany(
            "UPDATE player_talent_caps SET durability = %s WHERE player_id = %s", caps
        )
        cur.executemany(
            """UPDATE player_skills_history
               SET durability = LEAST(100, GREATEST(1, durability + %s))
               WHERE player_id = %s""",
            history,
        )
    _custom_teams(conn)


def _custom_teams(conn):
    from src.league.real_seasons import players as real_players

    for team in conn.execute("SELECT id, players FROM custom_teams").fetchall():
        entries = team["players"] or []
        changed = False
        for entry in entries:
            edited = entry.get("skills")
            if not edited:
                continue
            season = real_players.get(entry.get("key", ""))
            if season is None or season.pos not in PITCHER_POSITIONS:
                continue
            if int(edited.get("durability", 0)) <= OLD_MAX:
                edited["durability"] = season.skills["durability"]
                changed = True
        if changed:
            conn.execute(
                "UPDATE custom_teams SET players = %s WHERE id = %s",
                (Jsonb(entries), team["id"]),
            )
