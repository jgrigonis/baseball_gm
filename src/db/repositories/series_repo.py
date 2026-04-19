# src/db/repositories/series_repo.py


class SeriesRepository:
    def __init__(self, conn):
        self.conn = conn

    def get_champion(self, season_id: str, min_wins: int = 4) -> dict | None:
        """Return the Finals champion as {team_id, city, mascot}, or None if undecided."""
        finals = self.conn.execute(
            "SELECT id FROM series WHERE season_id = %s AND name = 'Finals'",
            (season_id,),
        ).fetchone()
        if not finals:
            return None
        champ = self.conn.execute(
            """SELECT winner_id, COUNT(*) as wins FROM games
               WHERE series_id = %s AND completed = 1
               GROUP BY winner_id ORDER BY wins DESC LIMIT 1""",
            (finals["id"],),
        ).fetchone()
        if not champ or champ["wins"] < min_wins:
            return None
        t = self.conn.execute(
            "SELECT city, mascot FROM teams WHERE id = %s", (champ["winner_id"],)
        ).fetchone()
        if not t:
            return None
        return {"team_id": champ["winner_id"], "city": t["city"], "mascot": t["mascot"]}

    def get_team_playoff_result(self, team_id: str, season_id: str) -> str | None:
        """Return a string like 'Won Finals' or 'Eliminated in 1v8', or None if no playoff appearance."""
        SERIES_ORDER = [
            ("Finals", 7),
            ("[1,8]v[4,5]", 7),
            ("[2,7]v[3,6]", 7),
            ("1v8", 5),
            ("2v7", 5),
            ("3v6", 5),
            ("4v5", 5),
        ]
        for series_name, best_of in SERIES_ORDER:
            sid_row = self.conn.execute(
                "SELECT id FROM series WHERE season_id = %s AND name = %s",
                (season_id, series_name),
            ).fetchone()
            if not sid_row:
                continue
            appeared = self.conn.execute(
                """SELECT 1 FROM games WHERE series_id = %s
                   AND (home_team_id = %s OR away_team_id = %s) LIMIT 1""",
                (sid_row["id"], team_id, team_id),
            ).fetchone()
            if not appeared:
                continue
            wins_needed = {5: 3, 7: 4}[best_of]
            wins_row = self.conn.execute(
                """SELECT COUNT(*) as wins FROM games
                   WHERE series_id = %s AND completed = 1 AND winner_id = %s""",
                (sid_row["id"], team_id),
            ).fetchone()
            my_wins = wins_row["wins"] if wins_row else 0
            if my_wins >= wins_needed:
                return f"Won {series_name}"
            else:
                if series_name in ["1v8", "2v7", "3v6", "4v5"]:
                    round = "first round: "
                elif series_name in ["[1,8]v[4,5]", "[2,7]v[3,6]"]:
                    round = "semi-finals round: "
                else:
                    round = ""
                return f"Eliminated in {round}{series_name}"
        return None
