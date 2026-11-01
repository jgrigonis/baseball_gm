# src/api/services/news/names.py
"""
Who's who for the news feed: team and player names, the GM running each
team, and how a player came to his team ("drafted by Josh in 2027",
"acquired by Josh in a 2028 trade"), so a story can credit, or blame, the
GM behind the move.
"""

from __future__ import annotations

from src.league import trade_deadline

# A trade made this many days before the deadline (or on it) is a deadline deal.
DEADLINE_DAYS = 7


def and_list(items: list[str]) -> str:
    if not items:
        return "nothing"
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def pretty(name: str) -> str:
    """Generated names are stored in capitals; stories read better in mixed
    case: "MCDONALD" -> "McDonald", "O'NEIL" -> "O'Neil". A name that's
    already mixed case is left as it is."""
    if not name or not name.isupper():
        return name or ""
    out = name.title()
    if out.startswith("Mc") and len(out) > 2:
        out = "Mc" + out[2].upper() + out[3:]
    return out


def possessive(name: str) -> str:
    return f"{name}'" if name.endswith("s") else f"{name}'s"


def is_deadline_deal(conn, season_id: str, on: str) -> bool:
    deadline = trade_deadline.deadline_date(conn, season_id)
    if not deadline or on > deadline:
        return False
    from datetime import date

    gap = (date.fromisoformat(deadline) - date.fromisoformat(on)).days
    return 0 <= gap <= DEADLINE_DAYS


class Names:
    def __init__(self, conn, league_id: str):
        self.conn = conn
        self.league_id = league_id
        rows = conn.execute(
            """SELECT DISTINCT t.id, t.city, t.mascot FROM teams t
               JOIN league_season_teams lst ON lst.team_id = t.id
               WHERE lst.league_id = %s""",
            (league_id,),
        ).fetchall()
        self._teams = {r["id"]: dict(r) for r in rows}
        gms = conn.execute(
            """SELECT id, team_id, display_name, is_ai, user_id, fired_at
               FROM gms WHERE league_id = %s""",
            (league_id,),
        ).fetchall()
        self._gms = {g["id"]: dict(g) for g in gms}
        # Who runs each team now: a person over an AI GM, a GM in the job
        # over a fired one.
        self._gm_of_team: dict[str, dict] = {}
        for g in sorted(gms, key=lambda g: (g["fired_at"] is None, not g["is_ai"])):
            if g["team_id"]:
                self._gm_of_team[g["team_id"]] = dict(g)
        self._players: dict[str, str] = {}
        self._origins: dict[tuple[str, str], tuple[str, list[str]]] = {}

    # ── Teams and GMs ────────────────────────────────────────────────────────

    def team(self, team_id: str | None) -> str:
        """The mascot, e.g. "Captains"; the short name headlines use."""
        t = self._teams.get(team_id or "")
        if not t:
            t = self._load_team(team_id)
        return t["mascot"] if t else "?"

    def full_team(self, team_id: str | None) -> str:
        t = self._teams.get(team_id or "") or self._load_team(team_id)
        return f"{t['city']} {t['mascot']}" if t else "?"

    def city(self, team_id: str | None) -> str:
        t = self._teams.get(team_id or "") or self._load_team(team_id)
        return t["city"] if t else "?"

    def _load_team(self, team_id: str | None) -> dict | None:
        if not team_id:
            return None
        row = self.conn.execute(
            "SELECT id, city, mascot FROM teams WHERE id = %s", (team_id,)
        ).fetchone()
        if row:
            self._teams[team_id] = dict(row)
        return self._teams.get(team_id)

    def gm_of(self, team_id: str | None) -> dict | None:
        return self._gm_of_team.get(team_id or "")

    def gm(self, gm_id: str | None) -> dict | None:
        return self._gms.get(gm_id or "")

    def gm_name(self, gm: dict | None) -> str | None:
        return gm["display_name"] if gm else None

    def gm_team(self, team_id: str) -> str:
        """ "Josh's Captains", or just "Captains" with no GM."""
        name = self.gm_name(self.gm_of(team_id))
        return (
            f"{possessive(name)} {self.team(team_id)}" if name else self.team(team_id)
        )

    def gm_ids(self, *team_ids: str | None) -> list[str]:
        return [g["id"] for t in team_ids if (g := self.gm_of(t))]

    def is_human(self, team_id: str | None) -> bool:
        g = self.gm_of(team_id)
        return bool(g and not g["is_ai"])

    # ── Players ──────────────────────────────────────────────────────────────

    def player(self, player_id: str) -> str:
        if player_id not in self._players:
            self.load_players([player_id])
        return self._players.get(player_id, "?")

    def last(self, player_id: str) -> str:
        return self.player(player_id).split(" ")[-1]

    def load_players(self, player_ids) -> None:
        todo = [p for p in set(player_ids) if p and p not in self._players]
        if not todo:
            return
        for r in self.conn.execute(
            "SELECT id, first_name, last_name FROM players WHERE id = ANY(%s)",
            (todo,),
        ).fetchall():
            self._players[r["id"]] = (
                f"{pretty(r['first_name'])} {pretty(r['last_name'])}"
            )

    # ── How a player got to his team ─────────────────────────────────────────

    def origin(self, player_id: str, team_id: str) -> tuple[str, list[str]]:
        """A phrase on how the player came to ``team_id`` and the GMs it
        credits, e.g. ("drafted by Josh in 2027", [gm_id]). The latest move
        counts: a trade after the draft is how he got there. ("", []) when
        neither a draft nor a trade in this league brought him."""
        key = (player_id, team_id)
        if key not in self._origins:
            self._origins[key] = self._origin(player_id, team_id)
        return self._origins[key]

    def _origin(self, player_id: str, team_id: str) -> tuple[str, list[str]]:
        trade = self.conn.execute(
            """SELECT o.from_team_id, o.to_team_id, o.from_gm_id, o.created_on,
                      o.season_id, s.year
               FROM trade_offer_items i
               JOIN trade_offers o ON o.id = i.offer_id
               JOIN seasons s ON s.id = o.season_id
               WHERE i.player_id = %s AND o.league_id = %s AND o.status = 'accepted'
                 AND i.from_team_id <> %s AND %s IN (o.from_team_id, o.to_team_id)
               ORDER BY o.created_on DESC, o.created_at DESC LIMIT 1""",
            (player_id, self.league_id, team_id, team_id),
        ).fetchone()
        if trade:
            gm = (
                self.gm(trade["from_gm_id"])
                if trade["from_team_id"] == team_id and trade["from_gm_id"]
                else self.gm_of(team_id)
            )
            if not gm:
                return "", []
            when = (
                "at the deadline"
                if is_deadline_deal(self.conn, trade["season_id"], trade["created_on"])
                else f"in a {trade['year']} trade"
            )
            return f"acquired by {gm['display_name']} {when}", [gm["id"]]
        pick = self.drafted(player_id)
        if not pick:
            return "", []
        gm = self.gm(pick["gm_id"])
        if not gm:
            return "", []
        if pick["team_id"] == team_id:
            return (
                f"drafted by {gm['display_name']} in {pick['year']}"
                f" (round {pick['round']})",
                [gm["id"]],
            )
        return (
            f"drafted by {gm['display_name']} of the {self.team(pick['team_id'])}"
            f" in {pick['year']}",
            [gm["id"]],
        )

    def drafted(self, player_id: str) -> dict | None:
        """The pick that took the player in this league's draft, if any."""
        row = self.conn.execute(
            """SELECT dp.gm_id, dp.team_id, dp.round, dp.pick_number, s.year
               FROM draft_picks dp
               JOIN drafts d ON d.id = dp.draft_id
               JOIN seasons s ON s.id = d.season_id
               WHERE dp.player_id = %s AND d.league_id = %s
               ORDER BY s.year DESC LIMIT 1""",
            (player_id, self.league_id),
        ).fetchone()
        return dict(row) if row else None
