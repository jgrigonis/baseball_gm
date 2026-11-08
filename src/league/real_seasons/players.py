# src/league/real_seasons/players.py
"""
Every real player-season worth picking for a custom team: 100+ plate
appearances or 30+ innings, 1871 on, from the Lahman Baseball Database.

scripts/real_rosters.py --export-players rates them the same way as a real
season league's players (era-relative, then onto our generated players'
scale) and writes data/players.tsv.gz. A player is one row per season:
pick "Ken Griffey 1997" and you get him as he was that year, at 27.
"""

from __future__ import annotations

import functools
import gzip
import random
import unicodedata
import uuid
from dataclasses import dataclass

from src.league.real_seasons import DATA_DIR, SKILLS
from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills

PLAYERS_FILE = DATA_DIR / "players.tsv.gz"


@dataclass(frozen=True)
class PlayerSeason:
    id: str  # Lahman playerID: the same man across his seasons
    year: int
    first: str
    last: str
    born: int | None
    age: int
    pos: str  # our affinity position that season
    bats: str
    throws: str
    teams: tuple[str, ...]  # his clubs that season (Lahman team codes)
    skills: dict[str, int]

    @property
    def key(self) -> str:
        """Names one player-season, e.g. "griffke02-1997"."""
        return f"{self.id}-{self.year}"

    @property
    def name(self) -> str:
        return f"{self.first} {self.last}".strip()

    def record(self, rng: random.Random) -> PlayerRecord:
        """A new game player built from this season."""
        return PlayerRecord(
            id=uuid.UUID(int=rng.getrandbits(128)).hex,
            first_name=self.first,
            last_name=self.last,
            bats=self.bats if self.bats in ("L", "R", "S") else "R",
            throws=self.throws if self.throws in ("L", "R") else "R",
            position=self.pos,
            skills=PlayerSkills(dict(self.skills), age=self.age),
        )


def _fold(text: str) -> str:
    """Lowercase without accents or punctuation, so "pena" finds Peña."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return "".join(c if c.isalnum() else " " for c in text.casefold())


def _parse(line: str, head: list[str]) -> PlayerSeason:
    row = dict(zip(head, line.rstrip("\n").split("\t")))
    return PlayerSeason(
        id=row["id"],
        year=int(row["year"]),
        first=row["first"],
        last=row["last"],
        born=int(row["born"]) if row["born"] else None,
        age=int(row["age"]),
        pos=row["pos"],
        bats=row["bats"],
        throws=row["throws"],
        teams=tuple(t for t in row["teams"].split("/") if t),
        skills={s: int(row[s]) for s in SKILLS},
    )


@functools.cache
def _all() -> tuple[tuple[PlayerSeason, ...], dict[str, PlayerSeason], list[str]]:
    with gzip.open(PLAYERS_FILE, "rt", encoding="utf-8") as f:
        head = f.readline().rstrip("\n").split("\t")
        seasons = tuple(_parse(line, head) for line in f if line.strip())
    by_key = {s.key: s for s in seasons}
    names = [_fold(s.name) for s in seasons]
    return seasons, by_key, names


def count() -> int:
    return len(_all()[0])


def get(key: str) -> PlayerSeason | None:
    """A player-season by its key ("griffke02-1997"), or None."""
    return _all()[1].get(key)


def search(query: str, limit: int = 50) -> tuple[list[PlayerSeason], int]:
    """Player-seasons whose name has every word of the query as the start of
    a word ("ken grif"), and a four-digit word, if any, as the year
    ("griffey 1997"). Sorted by last name, first name, then year. Returns at
    most `limit` of them and how many matched in all."""
    words = _fold(query).split()
    years = {int(w) for w in words if w.isdigit() and len(w) == 4}
    words = [w for w in words if not (w.isdigit() and len(w) == 4)]
    if not words and not years:
        return [], 0
    seasons, _, names = _all()
    found = []
    for s, name in zip(seasons, names):
        if years and s.year not in years:
            continue
        parts = name.split()
        if all(any(p.startswith(w) for p in parts) for w in words):
            found.append(s)
    found.sort(key=lambda s: (_fold(s.last), _fold(s.first), s.born or 0, s.year))
    return found[:limit], len(found)
