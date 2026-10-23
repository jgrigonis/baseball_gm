# scripts/diagnose_ground_out_probs.py
"""
Diagnostic: in-play outcome probabilities for runner-on-first situations.

Run with:
    python -m diagnose_ground_out_probs
    # or from the repo root:
    python scripts/diagnose_ground_out_probs.py

Prints a weight breakdown table for every combination of:
  - outs (0, 1)
  - runner configuration (empty, 1st only, 1st+2nd, 1st+3rd, loaded)

Highlights ground_out vs fielders_choice vs double_play to quantify
the probability leak reported in the bug.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from types import SimpleNamespace
from src.game.resolver import Resolver
from src.game.bases import FIRST, SECOND, THIRD
from src.game.intents.pitch import PrePitchSituation
from src.player.player_in_game import PlayerInGame
from src.player.player_skills import PlayerSkills
from src.team.lineup_slot import LineupSlot
from src.team.team_in_game_factory import TeamInGameFactory
from tests.factories.player_record_factory import make_player_record
from tests.factories.team_record_factory import make_team_record


def _uniform_skills(player: PlayerInGame, skill: int) -> None:
    """Replace a player's skills with a uniform value across all keys (immutable-safe)."""
    player.skills = PlayerSkills({k: skill for k in player.skills})


# ── minimal fake RNG ──────────────────────────────────────────────────────────


class ConstRNG:
    def __init__(self, v=0.5):
        self.v = v

    def random(self):
        return self.v

    def choice(self, seq):
        return seq[0]


# ── minimal game stub ─────────────────────────────────────────────────────────


class FakeBases:
    def __init__(self):
        self._r: dict = {}

    def runner_on(self, base):
        return self._r.get(base)

    def set_runner(self, base):
        self._r[base] = PlayerInGame(make_player_record())

    def clear(self):
        self._r = {}

    @property
    def is_empty(self):
        return not self._r

    @property
    def number_of_baserunners(self):
        return len(self._r)


def _make_game(outs: int, runner_bases: list[int], skill: int = 50) -> SimpleNamespace:
    """Build the minimal game object InPlayModifiers.apply_all needs."""
    rng = ConstRNG()
    bases = FakeBases()
    for b in runner_bases:
        bases.set_runner(b)

    # build a pitch_team with all positions filled at `skill`
    pitch_team = TeamInGameFactory.from_record(make_team_record())
    positions = {}
    for pos in ("c", "1b", "2b", "3b", "ss", "lf", "cf", "rf"):
        p = PlayerInGame(make_player_record(position=pos))
        _uniform_skills(p, skill)
        positions[pos] = p
        pitch_team.lineup.append(LineupSlot(player=p, position=pos))
    pitch_team._positions = positions

    pitcher = PlayerInGame(make_player_record(position="sp"))
    _uniform_skills(pitcher, skill)

    batter = PlayerInGame(make_player_record())
    _uniform_skills(batter, skill)

    def pos(position: str):
        return {"p": pitcher, **positions}[position]

    return SimpleNamespace(
        bases=bases,
        inning=SimpleNamespace(outs=outs),
        count=SimpleNamespace(balls=0, strikes=0),
        situation=PrePitchSituation(),
        # modifiers do game.current_batter.player to reach the PlayerInGame
        current_batter=SimpleNamespace(player=batter),
        pos=pos,
        score=SimpleNamespace(differential=0),
        rng=rng,
    )


# ── snapshot weights after all modifiers ─────────────────────────────────────


def snapshot_in_play_weights(
    outs: int, runner_bases: list[int], skill: int = 50
) -> dict:
    resolver = Resolver(rng=ConstRNG())
    game = _make_game(outs, runner_bases, skill)
    resolver.in_play_outcome.reset()
    resolver._apply_in_play_modifiers(game)
    # WeightedChoice stores weights in ._weights dict
    return dict(resolver.in_play_outcome.get_weights())


# ── formatting helpers ────────────────────────────────────────────────────────

OUTCOMES = [
    "ground_out",
    "fielders_choice",
    "double_play",
    "fly_out",
    "single",
    "double",
    "triple",
    "sac_fly",
    "sac_bunt",
    "triple_play",
]

HIGHLIGHT = {"ground_out", "fielders_choice", "double_play"}


def pct(w: dict, key: str) -> float:
    total = sum(max(v, 0) for v in w.values())
    if total == 0:
        return 0.0
    return 100.0 * max(w.get(key, 0), 0) / total


def print_table(label: str, weights: dict) -> None:
    total = sum(max(v, 0) for v in weights.values())
    print(f"\n{'─' * 60}")
    print(f"  {label}   (total weight: {total:.0f})")
    print(f"{'─' * 60}")
    print(f"  {'outcome':<20} {'weight':>8}  {'%':>6}")
    print(f"  {'─' * 20} {'─' * 8}  {'─' * 6}")
    for outcome in OUTCOMES:
        w = weights.get(outcome, 0)
        p = pct(weights, outcome)
        marker = " ◄" if outcome in HIGHLIGHT and w > 0 else ""
        print(f"  {outcome:<20} {w:>8.0f}  {p:>5.1f}%{marker}")
    print()


# ── scenarios ─────────────────────────────────────────────────────────────────

SCENARIOS = [
    ("empty bases, 0 outs", 0, []),
    ("runner on 1st, 0 outs", 0, [FIRST]),
    ("runner on 1st, 1 out", 1, [FIRST]),
    ("runners on 1st+2nd, 0 outs", 0, [FIRST, SECOND]),
    ("runners on 1st+2nd, 1 out", 1, [FIRST, SECOND]),
    ("runners on 1st+3rd, 0 outs", 0, [FIRST, THIRD]),
    ("runners on 1st+3rd, 1 out", 1, [FIRST, THIRD]),
    ("bases loaded, 0 outs", 0, [FIRST, SECOND, THIRD]),
    ("bases loaded, 1 out", 1, [FIRST, SECOND, THIRD]),
]


def run_diagnostics(skill: int = 50) -> None:
    print(f"\n{'=' * 60}")
    print(f"  IN-PLAY OUTCOME PROBABILITIES  (all skills = {skill})")
    print("  Outcomes of interest marked with ◄")
    print(f"{'=' * 60}")

    for label, outs, bases in SCENARIOS:
        w = snapshot_in_play_weights(outs, bases, skill)
        print_table(f"{label}", w)

    # Extra: show how ground-ball pitcher skill shifts the numbers
    print(f"\n{'=' * 60}")
    print("  EFFECT OF PITCHER 'ground_balls' SKILL")
    print("  Scenario: runner on 1st, 0 outs")
    print(f"{'=' * 60}")
    for gb_skill in (30, 50, 70, 90):
        w = snapshot_in_play_weights(outs=0, runner_bases=[FIRST], skill=gb_skill)
        go_pct = pct(w, "ground_out")
        fc_pct = pct(w, "fielders_choice")
        dp_pct = pct(w, "double_play")
        print(
            f"  ground_balls={gb_skill:>2}  →  "
            f"ground_out={go_pct:>5.1f}%  "
            f"fielders_choice={fc_pct:>5.1f}%  "
            f"double_play={dp_pct:>5.1f}%"
        )


if __name__ == "__main__":
    # Optionally pass a skill level as argv[1], e.g. `python diagnose... 70`
    skill = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    run_diagnostics(skill)
