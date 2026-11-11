# tests/api/test_playoff_progress.py
"""The sim card's bar in the playoffs fills in series wins per round
(sim_playoff._round_progress)."""

from src.api.services.sim_playoff import _round_progress


class _Repo:
    """Series by name with their (winner_id, wins) rows."""

    def __init__(self, wins: dict):
        self.wins = wins

    def get_series_id(self, season_id, name):
        return name if name in self.wins else None

    def get_win_count(self, sid):
        return [{"winner_id": w, "wins": n} for w, n in self.wins[sid]]


def test_progress_counts_the_leaders_wins_capped_at_the_clinch():
    repo = _Repo(
        {
            "1v8": [("A", 3), ("B", 1)],  # done: 3 of 3
            "2v7": [("C", 2), ("D", 2)],  # 2
            "3v6": [("E", 1)],  # 1
            "4v5": [],  # 0
        }
    )
    rounds = {r["name"]: r for r in _round_progress(repo, "S")}
    assert rounds["Round 1"] == {"name": "Round 1", "done": 6, "need": 12}
    # Later rounds aren't drawn yet: nothing done, but their wins count.
    assert rounds["Semifinals"] == {"name": "Semifinals", "done": 0, "need": 8}
    assert rounds["Finals"] == {"name": "Finals", "done": 0, "need": 4}
