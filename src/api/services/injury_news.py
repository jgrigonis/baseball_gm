# src/api/services/injury_news.py
#
# Tells each human GM about injuries on their own team during a sim: who got
# hurt and who came back. The news is stored per GM, so a GM who didn't run
# the sim still sees it the next time they open the league.

from __future__ import annotations

from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.notification_repo import NotificationRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository


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
                    notes.add(
                        gm_id,
                        "injury",
                        {
                            "name": v["name"],
                            "days": v["days"],
                            "is_pitcher": v["is_pitcher"],
                        },
                    )
            for pid, v in before.items():
                if pid not in after:
                    notes.add(
                        gm_id,
                        "returned",
                        {
                            "name": v["name"],
                            "is_pitcher": v["is_pitcher"],
                            "on_40man": status_repo.get_status(pid)
                            in ("26man", "40man"),
                        },
                    )


def take_injury_news(conn, gm_id: str) -> dict:
    """The GM's unseen injury news, in the shape the sim responses use, and
    marked seen."""
    news = NotificationRepository(conn).take_unseen(gm_id)
    return {
        "new_injuries": [_fields(n) for n in news if n["kind"] == "injury"],
        "returned": [_fields(n) for n in news if n["kind"] == "returned"],
    }


def _fields(note: dict) -> dict:
    return {k: v for k, v in note.items() if k != "kind"}
