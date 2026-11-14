# src/api/services/live_draft.py
#
# Long Form's live draft (Josh, 2026-11-14; docs/design/Master_design.md,
# "Long Form — Interactive Snake Draft"). The same snake order and pick
# rights as the Blitz draft, but each person makes their own picks:
#
#   - AI teams pick the moment they're on the clock, by their needs, as they
#     do in the Blitz draft (src/api/services/draft_execute.py).
#   - A person's team waits for them. In a multiplayer league each pick has
#     the league's pick timer (leagues.pick_timer_sec, default 90 seconds);
#     when it runs out, the scouts make the default pick. Nobody can pause
#     it. A one-person league has no timer.
#   - The default pick is what the team's draft strategy takes: the highest
#     pin still there, else the best prospect for its needs. A person who
#     is away (multiplayer), or who left the rest to the scouts, gets it
#     straight away.
#   - Everyone sees a short list for their next pick: the best players
#     likely still there when it comes up, with the default pick first.
#
# A one-person league starts the draft with the Start Draft button; a
# multiplayer one when everyone is ready (src/api/services/ready_check.py).
# After the last pick, the sim worker finishes it as it does the Blitz
# draft (finish_draft), and the league goes on to the preseason.
#
# Every change locks the draft row first, so a pick and a running-out clock
# can't both make the same pick.

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from src.api.services import front_office
from src.api.services.draft_needs import draft_strategies
from src.db.repositories.draft_repo import DraftRepository
from src.db.repositories.pick_rights_repo import PickRightsRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_repo import TeamRepository
from src.league.league_constants import LEAGUE_START_YEAR
from src.league.offseason.draft_strategy import DraftStrategy, StrategyScorer
from src.league.offseason.snake_draft import ROUNDS
from src.player.player_evaluator import PlayerEvaluator

log = logging.getLogger(__name__)

DEFAULT_PICK_TIMER = 90
PICK_TIMER_RANGE = (15, 600)
SHORT_LIST = 5
RECENT = 10


@dataclass(frozen=True)
class Slot:
    pick: int  # overall, from 1
    round: int
    team_id: str


def is_live(draft: dict | None) -> bool:
    return bool(draft and draft["format"] == "interactive")


def is_open(conn, league_id: str) -> bool:
    """A live draft has started and still has picks to make."""
    draft = DraftRepository(conn).get_current_for_league(league_id)
    return bool(is_live(draft) and draft["state"] == "open")


class LiveDraft:
    def __init__(self, conn, draft_id: str, lock: bool = False):
        self.conn = conn
        sql = "SELECT * FROM drafts WHERE id = %s" + (" FOR UPDATE" if lock else "")
        row = conn.execute(sql, (draft_id,)).fetchone()
        if not row:
            raise ValueError("No such draft.")
        self.draft = dict(row)
        self.id = draft_id
        self.league_id = self.draft["league_id"]
        self.repo = DraftRepository(conn)
        self._order = [r["team_id"] for r in self.repo.get_team_id_draft_order(draft_id)]
        year = SeasonRepository(conn).get_year(self.draft["season_id"])
        self.year = year["year"] if year else LEAGUE_START_YEAR
        self._owners = PickRightsRepository(conn).owners(self.league_id, self.year)
        self._scorer = None
        self._strategies = None

    # ── Order ─────────────────────────────────────────────────────────────

    @property
    def total(self) -> int:
        return ROUNDS * len(self._order)

    def slot(self, pick: int) -> Slot | None:
        n = len(self._order)
        if not n or pick < 1 or pick > self.total:
            return None
        rnd = (pick - 1) // n + 1
        i = (pick - 1) % n
        original = self._order[i] if rnd % 2 else self._order[n - 1 - i]
        return Slot(pick, rnd, self._owners.get((rnd, original), original))

    def current(self) -> Slot | None:
        if self.draft["state"] != "open":
            return None
        return self.slot(self.draft["current_pick"])

    def next_slot(self, team_id: str) -> Slot | None:
        """This team's next pick, from the one on the clock."""
        pick = self.draft["current_pick"]
        while pick <= self.total:
            s = self.slot(pick)
            if s.team_id == team_id:
                return s
            pick += 1
        return None

    # ── People ────────────────────────────────────────────────────────────

    def _people(self) -> dict[str, dict]:
        """{team_id: gm} for the teams people run now."""
        rows = self.conn.execute(
            """SELECT g.id, g.team_id, g.is_away, g.display_name, d.auto
               FROM gms g
               LEFT JOIN draft_order d ON d.draft_id = %s AND d.team_id = g.team_id
               WHERE g.league_id = %s AND NOT g.is_ai AND g.user_id IS NOT NULL
                 AND g.fired_at IS NULL AND g.team_id IS NOT NULL""",
            (self.id, self.league_id),
        ).fetchall()
        return {r["team_id"]: dict(r) for r in rows}

    def _multiplayer(self, people: dict) -> bool:
        return len(people) > 1

    def _waits_for(self, team_id: str, people: dict) -> bool:
        """Whether this team's pick waits for its person."""
        gm = people.get(team_id)
        if not gm or gm["auto"]:
            return False
        return not (self._multiplayer(people) and gm["is_away"])

    # ── The pool ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._scorer is not None:
            return
        rated = sorted(
            (
                (p, PlayerEvaluator.prospect_rating(p.skills))
                for p in self.repo.get_pool_records(self.league_id, self.id)
            ),
            key=lambda x: x[1],
            reverse=True,
        )
        self._scorer = StrategyScorer(rated) if rated else None
        self._records = {p.id: p for p, _ in rated}
        self._strategies = draft_strategies(
            self.conn, self.id, self.league_id, cached=False
        )

    def picks(self) -> list[dict]:
        return [
            dict(r)
            for r in self.conn.execute(
                """SELECT pick_number, round, team_id, player_id, auto_picked
                   FROM draft_picks WHERE draft_id = %s ORDER BY pick_number""",
                (self.id,),
            ).fetchall()
        ]

    def available(self) -> set[str]:
        self._load()
        if not self._scorer:
            return set()
        taken = {p["player_id"] for p in self.picks()}
        return {pid for pid in self._scorer.order if pid not in taken}

    def strategy(self, team_id: str, made: list[dict] | None = None) -> DraftStrategy:
        """The team's strategy as it stands now: its needs wear off for the
        picks it has made this draft, as they do in the Blitz draft."""
        self._load()
        base = self._strategies.get(team_id) or DraftStrategy()
        s = base.copy()
        for p in made if made is not None else self.picks():
            if p["team_id"] == team_id and p["player_id"] in self._scorer.prospect:
                self._scorer.wear_off(p["player_id"], s)
        return s

    def default_pick(self, team_id: str) -> str | None:
        """Who the team takes if nobody chooses: its strategy's pick."""
        available = self.available()
        if not available:
            return None
        return self._scorer.choose(available, self.strategy(team_id))

    # ── Making picks ──────────────────────────────────────────────────────

    def start(self) -> None:
        """Open the draft and make the AI picks up to the first person's."""
        if self.draft["state"] != "pending":
            raise ValueError("The draft has already started.")
        self.conn.execute(
            "UPDATE drafts SET state = 'open', current_pick = 1 WHERE id = %s",
            (self.id,),
        )
        self.draft["state"] = "open"
        self.draft["current_pick"] = 1
        self.advance()

    def pick(self, team_id: str, player_id: str) -> None:
        """A person's pick. Raises ValueError if it isn't theirs to make or
        he isn't there to take."""
        slot = self.current()
        if not slot:
            raise ValueError("The draft isn't on.")
        if slot.team_id != team_id:
            raise ValueError("It isn't your pick.")
        if player_id not in self.available():
            raise ValueError("He's already been picked.")
        self._make(slot, player_id, auto=False)
        self.advance()

    def scouts_pick(self, team_id: str, rest: bool = False) -> None:
        """The default pick for this team now (it must be on the clock), or
        with rest, every pick it has left."""
        if rest:
            self.conn.execute(
                "UPDATE draft_order SET auto = TRUE WHERE draft_id = %s AND team_id = %s",
                (self.id, team_id),
            )
        slot = self.current()
        if slot and slot.team_id == team_id:
            self._make(slot, self.default_pick(team_id), auto=True)
            self.advance()

    def take_over(self, team_id: str) -> None:
        """A person takes their picks back from the scouts."""
        self.conn.execute(
            "UPDATE draft_order SET auto = FALSE WHERE draft_id = %s AND team_id = %s",
            (self.id, team_id),
        )

    def expire(self) -> bool:
        """If the clock on the current pick has run out, the scouts make it.
        Returns True if they did."""
        slot = self.current()
        deadline = self.draft.get("pick_deadline")
        if not slot or not deadline or deadline > datetime.now(UTC):
            return False
        log.info("Draft %s: pick %s ran out of time", self.id, slot.pick)
        self._make(slot, self.default_pick(slot.team_id), auto=True)
        self.advance()
        return True

    def advance(self) -> None:
        """Make every pick that doesn't wait for a person, then start the
        clock on the next one (multiplayer), or note the draft is done."""
        people = self._people()
        while True:
            slot = self.current()
            pid = self.default_pick(slot.team_id) if slot else None
            if not slot or not pid:
                self._picks_done()
                return
            if self._waits_for(slot.team_id, people):
                break
            self._make(slot, pid, auto=True)
        timer = self._timer() if self._multiplayer(people) else None
        self.conn.execute(
            """UPDATE drafts SET pick_deadline = CASE WHEN %s::int IS NULL THEN NULL
                   ELSE NOW() + %s::int * INTERVAL '1 second' END
               WHERE id = %s""",
            (timer, timer, self.id),
        )
        self.draft["pick_deadline"] = self.conn.execute(
            "SELECT pick_deadline FROM drafts WHERE id = %s", (self.id,)
        ).fetchone()["pick_deadline"]

    def _timer(self) -> int:
        row = self.conn.execute(
            "SELECT pick_timer_sec FROM leagues WHERE id = %s", (self.league_id,)
        ).fetchone()
        return (row and row["pick_timer_sec"]) or DEFAULT_PICK_TIMER

    def _make(self, slot: Slot, player_id: str, auto: bool) -> None:
        gm = self.conn.execute(
            "SELECT id FROM gms WHERE league_id = %s AND team_id = %s",
            (self.league_id, slot.team_id),
        ).fetchone()
        self.repo.insert_draft_picks(
            self.id,
            slot.pick,
            slot.round,
            gm["id"] if gm else None,
            slot.team_id,
            player_id,
            auto,
            datetime.now(UTC).isoformat(),
        )
        TeamRepository(self.conn).add_player(slot.team_id, player_id)
        PlayerStatusRepository(self.conn).set_status(player_id, "minors")
        self.draft["current_pick"] = slot.pick + 1
        self.conn.execute(
            "UPDATE drafts SET current_pick = %s, pick_deadline = NULL WHERE id = %s",
            (slot.pick + 1, self.id),
        )
        self.draft["pick_deadline"] = None

    def _picks_done(self) -> None:
        """No picks left (or nobody left to pick): the sim worker finishes
        the draft."""
        from src.api.services import sim_jobs
        from src.db.locks import LeagueBusy

        self.conn.execute(
            "UPDATE drafts SET pick_deadline = NULL, current_pick = %s WHERE id = %s",
            (self.total + 1, self.id),
        )
        self.draft["current_pick"] = self.total + 1
        try:
            sim_jobs.submit(self.conn, self.league_id, "draft")
        except LeagueBusy:
            pass  # already queued

    @property
    def done(self) -> bool:
        return self.draft["state"] == "complete" or (
            self.draft["state"] == "open" and self.draft["current_pick"] > self.total
        )

    # ── What the draft room shows ─────────────────────────────────────────

    def short_list(self, team_id: str, n: int = SHORT_LIST) -> dict | None:
        """The team's next pick: which it is, how many picks away, the
        default pick, and the best players likely still there, the default
        first. Other teams are assumed to take their own default picks
        until then."""
        mine = self.next_slot(team_id)
        if not mine:
            return None
        available = self.available()
        made = self.picks()
        current = self.draft["current_pick"]
        working: dict[str, DraftStrategy] = {}
        for pick in range(current, mine.pick):
            s = self.slot(pick)
            st = working.get(s.team_id) or self.strategy(s.team_id, made)
            working[s.team_id] = st
            pid = self._scorer.choose(available, st)
            if not pid:
                break
            self._scorer.wear_off(pid, st)
            available.discard(pid)
        st = self.strategy(team_id, made)
        default = self._scorer.choose(available, st) if available else None
        best = sorted(
            (pid for pid in available if pid != default),
            key=lambda pid: self._scorer.score(pid, st),
            reverse=True,
        )
        return {
            "pick": mine.pick,
            "round": mine.round,
            "away": mine.pick - current,
            "default": default,
            "players": ([default] if default else []) + best[: n - 1],
        }

    def state(self, team_id: str | None) -> dict:
        """The draft room's poll: the pick on the clock, the clock, and the
        latest picks."""
        slot = self.current()
        people = self._people()
        names = _team_names(self.conn, self._order)
        made = self.picks()
        seconds = None
        if slot and self.draft.get("pick_deadline"):
            seconds = max(
                0,
                round((self.draft["pick_deadline"] - datetime.now(UTC)).total_seconds()),
            )
        players = _player_names(self.conn, [p["player_id"] for p in made[-RECENT:]])
        on = None
        if slot and not self.done:
            gm = people.get(slot.team_id)
            on = {
                "pick": slot.pick,
                "round": slot.round,
                "team_id": slot.team_id,
                "team": names.get(slot.team_id, ""),
                "gm": gm["display_name"] if gm else None,
                "you": slot.team_id == team_id,
            }
        mine = people.get(team_id) if team_id else None
        return {
            "state": self.draft["state"],
            "done": self.done or self.draft["state"] == "complete",
            "pick": self.draft["current_pick"],
            "total": self.total,
            "on_clock": on,
            "seconds_left": seconds,
            "timer": self._timer() if self._multiplayer(people) else None,
            "auto": bool(mine and mine["auto"]),
            "taken": [p["player_id"] for p in made],
            "recent": [
                {
                    "pick": p["pick_number"],
                    "round": p["round"],
                    "team": names.get(p["team_id"], ""),
                    "mine": p["team_id"] == team_id,
                    "auto": p["auto_picked"],
                    **players.get(p["player_id"], {"player_id": p["player_id"]}),
                }
                for p in reversed(made[-RECENT:])
            ],
        }


def _team_names(conn, team_ids: list[str]) -> dict[str, str]:
    rows = conn.execute(
        "SELECT id, city, mascot FROM teams WHERE id = ANY(%s)", (team_ids,)
    ).fetchall()
    return {r["id"]: f"{r['city']} {r['mascot']}" for r in rows}


def _player_names(conn, player_ids: list[str]) -> dict[str, dict]:
    rows = conn.execute(
        """SELECT id, first_name, last_name, position FROM players
           WHERE id = ANY(%s)""",
        (player_ids,),
    ).fetchall()
    return {
        r["id"]: {
            "player_id": r["id"],
            "name": f"{r['first_name']} {r['last_name']}",
            "position": r["position"],
        }
        for r in rows
    }


# ── Entry points ──────────────────────────────────────────────────────────────


def for_league(conn, league_id: str, lock: bool = False) -> LiveDraft | None:
    draft = DraftRepository(conn).get_current_for_league(league_id)
    if not is_live(draft) or draft["state"] == "complete":
        return None
    return LiveDraft(conn, draft["id"], lock=lock)


def expire_due(conn) -> int:
    """Make the picks whose clocks have run out, in every league. The sim
    worker calls this on its clock. Returns how many it made."""
    from src.db.connection import rollback_quietly

    rows = conn.execute(
        """SELECT id FROM drafts WHERE state = 'open' AND format = 'interactive'
             AND pick_deadline IS NOT NULL AND pick_deadline <= NOW()"""
    ).fetchall()
    conn.commit()
    made = 0
    for r in rows:
        try:
            if LiveDraft(conn, r["id"], lock=True).expire():
                made += 1
            conn.commit()
        except Exception:
            log.exception("Draft %s: the pick clock couldn't make its pick", r["id"])
            rollback_quietly(conn)
    return made


def finish(conn, draft_id: str) -> None:
    """After the last pick: AI rosters, then everything the Blitz draft does
    once its picks are in (finish_draft)."""
    from src.api.services.draft_execute import BlitzDraft, finish_draft
    from src.db.repositories.gm_repo import GMRepository

    live = LiveDraft(conn, draft_id, lock=True)
    if live.draft["state"] != "open":
        return
    draft = live.draft
    league_id = live.league_id
    human = GMRepository(conn).get_human_team_ids(league_id)
    outlooks = front_office.outlooks(conn, league_id, draft["season_id"])
    rosters = BlitzDraft(conn, league_id, human, outlooks=outlooks)
    rosters._reassign_rosters([{"team_id": t} for t in live._order])
    made = live.picks()
    DraftRepository(conn).set_complete_current_pick(draft_id, len(made) + 1)
    conn.execute("UPDATE drafts SET pick_deadline = NULL WHERE id = %s", (draft_id,))
    finish_draft(conn, draft, human, outlooks)
