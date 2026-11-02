# src/api/services/injury_news.py
#
# Tells each human GM about injuries on their own team during a sim: who got
# hurt and who came back. The news is stored per GM, so a GM who didn't run
# the sim still sees it the next time they open the league.

from __future__ import annotations

from src.api.view_models.player_cards import compute_ratings
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.notification_repo import NotificationRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.player.injury_types import injury_label
from src.player.positions import is_pitcher


class InjuryNews:
    """Snapshot every human team's injured list before a sim; call record()
    after it to store each GM's new injuries and returns."""

    def __init__(self, conn, league_id: str):
        self.conn = conn
        self.inj_repo = InjuryRepository(conn, league_id)
        self.gm_teams = GMRepository(conn).get_human_gm_teams(league_id)
        self.before = {
            gm_id: self.inj_repo.get_active_for_team(team_id)
            for gm_id, team_id in self.gm_teams.items()
        }

    def record(self) -> None:
        notes = NotificationRepository(self.conn)
        status_repo = PlayerStatusRepository(self.conn)
        for gm_id, team_id in self.gm_teams.items():
            before = self.before[gm_id]
            after = self.inj_repo.get_active_for_team(team_id)
            for pid, v in after.items():
                if pid not in before:
                    note = {
                        "name": v["name"],
                        "days": v["days"],
                        "is_pitcher": self._is_pitcher(pid, v),
                    }
                    if v.get("injury_type"):
                        note["injury"] = injury_label(v["injury_type"])
                    notes.add(gm_id, "injury", note)
            for pid, v in before.items():
                if pid not in after:
                    notes.add(
                        gm_id,
                        "returned",
                        {
                            "name": v["name"],
                            # How long the injury was, in days
                            "length": v["length"],
                            "is_pitcher": self._is_pitcher(pid, v),
                            "on_40man": status_repo.get_status(pid)
                            in ("26man", "40man"),
                        },
                    )

    def _is_pitcher(self, player_id: str, injury: dict) -> bool:
        """Whether the alert should link to the pitching tab for this player.

        Go by this season's usage when there is any. A player with no innings
        and no at-bats (e.g. hurt since last season) is classified the way the
        lineup tab does it, by whether the pitching or hitting rating is
        higher, falling back to the listed position if there are no skills."""
        outs, ab = injury["outs"], injury["ab"]
        if outs or ab:
            return outs > 0 and (ab == 0 or outs / 3 >= ab / 10)
        row = PlayerRepository(self.conn).get_with_skills(player_id)
        # player_id only comes from the player_skills side of the join
        if row and row.get("player_id"):
            ratings = compute_ratings(row, row.get("throws") or "R")
            if ratings:
                pitching = max(ratings.get("sp", 0), ratings.get("rp", 0))
                return pitching > ratings.get("overall_player", 0)
        return is_pitcher(injury["position"] or "")


def take_injury_news(conn, gm_id: str) -> dict:
    """The GM's unseen injury news, in the shape the sim responses use, and
    marked seen."""
    news = NotificationRepository(conn).take_unseen(gm_id)
    return {
        "new_injuries": [_fields(n) for n in news if n["kind"] == "injury"],
        "returned": [_fields(n) for n in news if n["kind"] == "returned"],
        # Players the game moved to keep the roster between 25 and 40
        "roster_moves": [_fields(n) for n in news if n["kind"] == "roster"],
        # Trade offers, answers and votes (src/api/services/trades.py)
        "trades": [_fields(n) for n in news if n["kind"] == "trade"],
    }


def _fields(note: dict) -> dict:
    return {k: v for k, v in note.items() if k != "kind"}
