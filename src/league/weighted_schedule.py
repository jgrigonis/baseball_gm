# src/league/weighted_schedule.py
"""
A weighted season: more games against division rivals, fewer against the
other league, like MLB. Used by leagues that have two leagues of divisions
(src/league/divisions.py) and the weighted schedule setting on.

The season is a list of rounds. Every round is a set of series that covers
every team exactly once, all the same length (2, 3 or 4 games), so every team
plays every day and the season comes out at exactly the target for everyone.
Rounds come from three kinds of block:

- League blocks: a round robin inside each league, both leagues at once.
  Every pair in the same league meets once. With an odd number of teams in a
  league (15 in the 30-team world league) one team per league sits out each
  round, and the two that sit out play each other instead.
- Division blocks: a round robin inside every division at once. With odd
  divisions the team left out of each division plays the one left out of a
  division in the other league.
- Interleague blocks: one round is a fixed pairing of every team with a team
  from the other league. There are as many pairings as teams per league, and
  together they cover every interleague pair once.

The teams left out of league and division blocks play one of the interleague
pairings over the block, so those games count toward it. The interleague
rounds then top every pairing up as evenly as the target allows. Division
and same-league pairs all get the same number of games. Interleague pairs
get the same number give or take a few.
"""

from __future__ import annotations

import random

# Series lengths for each league size: (league blocks, division blocks).
# Each number is one block whose series are that many games. Every pair in a
# league plays the league blocks' total; division rivals also play the
# division blocks'. Interleague games fill the rest of the season.
#
# Games against each opponent, (division, rest of league, other league):
#   16: 18 / 13 / 7     20: 13 / 10 / 6     24: 12 / 7 / 5
#   28: 13 /  6 / 3     30: 13 /  5 / 4     32:  8 / 5 / about 4
BLOCKS: dict[int, tuple[list[int], list[int]]] = {
    16: ([3, 3, 3, 4], [2, 3]),
    20: ([3, 3, 4], [3]),
    24: ([3, 4], [2, 3]),
    28: ([3, 3], [3, 4]),
    30: ([2, 3], [4, 4]),
    32: ([2, 3], [3]),
}

# How a number of interleague games against one pairing splits into series.
_SPLITS = {
    0: [],
    2: [2],
    3: [3],
    4: [4],
    5: [2, 3],
    6: [3, 3],
    7: [3, 4],
    8: [4, 4],
    9: [3, 3, 3],
    10: [3, 3, 4],
    11: [3, 4, 4],
    12: [4, 4, 4],
}

Round = tuple[list[tuple[str, str]], int]


def supports(num_teams: int) -> bool:
    return num_teams in BLOCKS


def _circle(m: int) -> list[list[tuple[int, int | None]]]:
    """Round robin rounds over indices 0..m-1, circle method. With m odd,
    each round has one index paired with None: it sits that round out.
    Every round lists the pairs in the same order of positions, so two
    lists of the same size run through it in step."""
    n = m + (m % 2)
    idx: list[int | None] = list(range(m)) + ([None] if m % 2 else [])
    fixed, rotating = idx[-1], idx[:-1]
    rounds = []
    for _ in range(n - 1):
        pairs = [(rotating[0], fixed)]
        for i in range(1, n // 2):
            pairs.append((rotating[i], rotating[-i]))
        rounds.append([(a, b) if a is not None else (b, a) for a, b in pairs])
        rotating = rotating[-1:] + rotating[:-1]
    return rounds


class WeightedSchedule:
    def __init__(self, leagues: list[list[list[str]]], rng: random.Random):
        """leagues: two leagues, each a list of divisions, each a list of
        team ids. Both leagues need the same number of divisions, all the
        same size."""
        if len(leagues) != 2:
            raise ValueError("A weighted schedule needs two leagues")
        sizes = {len(d) for lg in leagues for d in lg}
        if len(sizes) != 1 or len(leagues[0]) != len(leagues[1]):
            raise ValueError("Every division needs the same number of teams")
        self.rng = rng
        self.s = sizes.pop()
        self.d = len(leagues[0])
        self.h = self.s * self.d  # teams per league
        # Each league as one list, division by division.
        self.a = [t for div in leagues[0] for t in div]
        self.b = [t for div in leagues[1] for t in div]
        self.n = 2 * self.h
        # Interleague games so far on each pairing k: a[i] vs b[(i+k) % h].
        self.pairing_games = [0] * self.h

    def pairing(self, k: int) -> list[tuple[str, str]]:
        return [(self.a[i], self.b[(i + k) % self.h]) for i in range(self.h)]

    def _pick_pairing(self, allowed: list[int]) -> int:
        low = min(self.pairing_games[k] for k in allowed)
        return self.rng.choice([k for k in allowed if self.pairing_games[k] == low])

    def _league_block(self, length: int) -> list[Round]:
        k = self._pick_pairing(list(range(self.h))) if self.h % 2 else 0
        b = [self.b[(i + k) % self.h] for i in range(self.h)]
        rounds = []
        for pairs in _circle(self.h):
            out = []
            for i, j in pairs:
                if j is None:  # both leagues' i sits out: they meet
                    out.append((self.a[i], b[i]))
                else:
                    out.append((self.a[i], self.a[j]))
                    out.append((b[i], b[j]))
            rounds.append((out, length))
        if self.h % 2:
            self.pairing_games[k] += length
        return rounds

    def _division_block(self, length: int) -> list[Round]:
        shift = 0
        if self.s % 2:
            k = self._pick_pairing([m * self.s for m in range(self.d)])
            shift = k // self.s
        rounds = []
        for pairs in _circle(self.s):
            out = []
            for div in range(self.d):
                a0 = div * self.s
                b0 = ((div + shift) % self.d) * self.s
                for i, j in pairs:
                    if j is None:
                        out.append((self.a[a0 + i], self.b[b0 + i]))
                    else:
                        out.append((self.a[a0 + i], self.a[a0 + j]))
                        out.append((self.b[b0 + i], self.b[b0 + j]))
            rounds.append((out, length))
        if self.s % 2:
            self.pairing_games[shift * self.s] += length
        return rounds

    def _interleague_adds(self, games: int) -> list[int]:
        """Games to add to each pairing, as even as the splits allow,
        totalling ``games``."""
        cur = self.pairing_games
        target = (games + sum(cur)) / self.h
        options = sorted(_SPLITS)
        # best[k][r]: least cost to give pairings k.. exactly r games
        inf = float("inf")
        best = [[inf] * (games + 1) for _ in range(self.h + 1)]
        choice = [[0] * (games + 1) for _ in range(self.h)]
        best[self.h][0] = 0.0
        for k in range(self.h - 1, -1, -1):
            for r in range(games + 1):
                for add in options:
                    if add > r or best[k + 1][r - add] == inf:
                        continue
                    cost = (cur[k] + add - target) ** 2 + best[k + 1][r - add]
                    if cost < best[k][r]:
                        best[k][r], choice[k][r] = cost, add
        if best[0][games] == inf:
            raise ValueError(f"Can't fit {games} interleague games")
        adds, r = [], games
        for k in range(self.h):
            adds.append(choice[k][r])
            r -= choice[k][r]
        return adds

    def rounds(self, target_games: int) -> list[Round]:
        league_lengths, division_lengths = BLOCKS[self.n]
        rounds: list[Round] = []
        for length in league_lengths:
            rounds += self._league_block(length)
        for length in division_lengths:
            rounds += self._division_block(length)
        played = sum(length for _, length in rounds)
        for k, add in enumerate(self._interleague_adds(target_games - played)):
            for length in _SPLITS[add]:
                rounds.append((self.pairing(k), length))
                self.pairing_games[k] += length
        rounds = self._order(rounds)
        return self._home_and_away(rounds)

    def _order(self, rounds: list[Round]) -> list[Round]:
        """A random order, picking the one of several tries with the fewest
        back-to-back series against the same team."""

        def repeats(order: list[Round]) -> int:
            count = 0
            for (prev, _), (cur, _) in zip(order, order[1:]):
                seen = {frozenset(p) for p in prev}
                count += sum(frozenset(p) in seen for p in cur)
            return count

        best, best_count = None, None
        for _ in range(40):
            order = rounds[:]
            self.rng.shuffle(order)
            count = repeats(order)
            if best_count is None or count < best_count:
                best, best_count = order, count
            if count == 0:
                break
        return best

    def _home_and_away(self, rounds: list[Round]) -> list[Round]:
        """Pick the home team of every series. A first pass gives each to
        whoever has hosted the other for fewer games, then whoever has fewer
        home games. Then series are flipped while that brings teams closer
        to half their games at home without splitting a matchup unevenly."""
        home = {t: 0 for t in self.a + self.b}
        hosted: dict[tuple[str, str], int] = {}
        series: list[list] = []  # [home, visitor, length, round index]
        for r, (pairs, length) in enumerate(rounds):
            for x, y in pairs:
                hx, hy = hosted.get((x, y), 0), hosted.get((y, x), 0)
                if hx != hy:
                    h, v = (x, y) if hx < hy else (y, x)
                elif home[x] != home[y]:
                    h, v = (x, y) if home[x] < home[y] else (y, x)
                else:
                    h, v = (x, y) if self.rng.random() < 0.5 else (y, x)
                hosted[(h, v)] = hosted.get((h, v), 0) + length
                home[h] += length
                series.append([h, v, length, r])

        half = sum(length for _, length in rounds) / 2

        def flip_gain(h: str, v: str, length: int) -> float:
            before = (home[h] - half) ** 2 + (home[v] - half) ** 2
            after = (home[h] - length - half) ** 2 + (home[v] + length - half) ** 2
            # The matchup's split: h hosts hosted[(h, v)], v hosts the rest.
            gap = hosted[(h, v)] - hosted.get((v, h), 0)
            pair_before, pair_after = gap**2, (gap - 2 * length) ** 2
            return before - after + 2 * (pair_before - pair_after)

        for _ in range(20):
            improved = False
            self.rng.shuffle(series)
            for sr in series:
                h, v, length, _ = sr
                if flip_gain(h, v, length) > 0:
                    home[h] -= length
                    home[v] += length
                    hosted[(h, v)] -= length
                    hosted[(v, h)] = hosted.get((v, h), 0) + length
                    sr[0], sr[1] = v, h
                    improved = True
            if not improved:
                break

        out: list[Round] = [([], length) for _, length in rounds]
        for h, v, _, r in series:
            out[r][0].append((h, v))
        for pairs, _ in out:
            self.rng.shuffle(pairs)
        return out
