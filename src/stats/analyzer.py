# src/stats/analyzer.py
from typing import List, Dict, Any, Callable
from dataclasses import dataclass


class StatsAnalyzer:
    """Analyze and rank player statistics across games"""

    def __init__(self, players):
        """
        Args:
            players: List of PlayerInGame objects with game_stats
        """
        self.players = players

    # ============ BATTING LEADERBOARDS ============

    def leaderboard_home_runs(self, min_at_bats=0) -> List[Dict[str, Any]]:
        """Get players ranked by home runs"""
        leaders = []

        for p in self.players:
            ab = p.game_stats.batting.at_bats
            if ab >= min_at_bats:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "home_runs": p.game_stats.batting.home_runs,
                        "at_bats": ab,
                    }
                )

        return sorted(leaders, key=lambda x: x["home_runs"], reverse=True)

    def leaderboard_rbi(self, min_at_bats=0) -> List[Dict[str, Any]]:
        """Get players ranked by RBIs"""
        leaders = []

        for p in self.players:
            ab = p.game_stats.batting.at_bats
            if ab >= min_at_bats:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "rbi": p.game_stats.batting.rbi,
                        "at_bats": ab,
                    }
                )

        return sorted(leaders, key=lambda x: x["rbi"], reverse=True)

    def leaderboard_hits(self, min_at_bats=0) -> List[Dict[str, Any]]:
        """Get players ranked by total hits"""
        leaders = []

        for p in self.players:
            ab = p.game_stats.batting.at_bats
            if ab >= min_at_bats:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "hits": p.game_stats.batting.hits,
                        "at_bats": ab,
                    }
                )

        return sorted(leaders, key=lambda x: x["hits"], reverse=True)

    def leaderboard_batting_average(self, min_at_bats=10) -> List[Dict[str, Any]]:
        """Get players ranked by batting average"""
        leaders = []

        for p in self.players:
            ab = p.game_stats.batting.at_bats
            if ab >= min_at_bats:
                hits = p.game_stats.batting.hits
                avg = hits / ab if ab > 0 else 0.0
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "avg": avg,
                        "hits": hits,
                        "at_bats": ab,
                    }
                )

        return sorted(leaders, key=lambda x: x["avg"], reverse=True)

    def leaderboard_on_base_percentage(
        self, min_plate_appearances=10
    ) -> List[Dict[str, Any]]:
        """Get players ranked by on-base percentage (OBP)"""
        leaders = []

        for p in self.players:
            stats = p.game_stats.batting

            # OBP = (H + BB + HBP) / (AB + BB + HBP + SF)

            numerator = stats.hits + stats.walks + stats.hbp
            denominator = stats.at_bats + stats.walks + stats.hbp + stats.sac_flys

            if denominator >= min_plate_appearances:
                obp = numerator / denominator if denominator > 0 else 0.0
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "obp": obp,
                        "hits": stats.hits,
                        "walks": stats.walks,
                        "plate_appearances": denominator,
                    }
                )

        return sorted(leaders, key=lambda x: x["obp"], reverse=True)

    def leaderboard_slugging_percentage(self, min_at_bats=10) -> List[Dict[str, Any]]:
        """Get players ranked by slugging percentage (SLG)"""
        leaders = []

        for p in self.players:
            stats = p.game_stats.batting
            ab = stats.at_bats

            if ab >= min_at_bats:
                # SLG = Total Bases / AB
                total_bases = (
                    stats.singles
                    + 2 * stats.doubles
                    + 3 * stats.triples
                    + 4 * stats.home_runs
                )
                slg = total_bases / ab if ab > 0 else 0.0

                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "slg": slg,
                        "total_bases": total_bases,
                        "at_bats": ab,
                    }
                )

        return sorted(leaders, key=lambda x: x["slg"], reverse=True)

    def leaderboard_ops(self, min_at_bats=10) -> List[Dict[str, Any]]:
        """Get players ranked by OPS (On-base Plus Slugging)"""
        leaders = []

        for p in self.players:
            stats = p.game_stats.batting
            ab = stats.at_bats

            if ab >= min_at_bats:
                # Calculate OBP
                obp_numerator = stats.hits + stats.walks + stats.hbp
                obp_denominator = ab + stats.walks + stats.hbp + stats.sac_flys
                obp = obp_numerator / obp_denominator if obp_denominator > 0 else 0.0

                # Calculate SLG
                total_bases = (
                    stats.singles
                    + 2 * stats.doubles
                    + 3 * stats.triples
                    + 4 * stats.home_runs
                )
                slg = total_bases / ab if ab > 0 else 0.0

                ops = obp + slg

                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "ops": ops,
                        "obp": obp,
                        "slg": slg,
                        "at_bats": ab,
                    }
                )

        return sorted(leaders, key=lambda x: x["ops"], reverse=True)

    def leaderboard_stolen_bases(self, min_at_bats=0) -> List[Dict[str, Any]]:
        """Get players ranked by stolen bases"""
        leaders = []

        for p in self.players:
            ab = p.game_stats.batting.at_bats
            if ab >= min_at_bats:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "stolen_bases": p.game_stats.batting.stolen_bases,
                        "caught_stealing": p.game_stats.batting.caught_stealing,
                        "at_bats": ab,
                    }
                )

        return sorted(leaders, key=lambda x: x["stolen_bases"], reverse=True)

    # ============ PITCHING LEADERBOARDS ============

    # def leaderboard_wins(self, min_innings=0) -> List[Dict[str, Any]]:
    #     """Get pitchers ranked by wins"""
    #     leaders = []

    #     for p in self.players:
    #         ip = p.game_stats.pitching.ip_float
    #         if ip >= min_innings:
    #             leaders.append({
    #                 'player': p,
    #                 'player_name': getattr(p, 'name', str(p.id)),
    #                 #'wins': p.game_stats.pitching.wins,
    #                 #'losses': p.game_stats.pitching.losses,
    #                 'innings': ip,
    #             })

    #     return sorted(leaders, key=lambda x: x['wins'], reverse=True)

    def leaderboard_era(self, min_innings=5.0) -> List[Dict[str, Any]]:
        """Get pitchers ranked by ERA (lower is better)"""
        leaders = []

        for p in self.players:
            stats = p.game_stats.pitching
            innings = stats.ip_float

            if innings >= min_innings:
                # ERA = (Earned Runs / Innings Pitched) * 9
                era = (stats.runs / innings * 9) if innings > 0 else 0.0

                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "era": era,
                        "innings": innings,
                        "earned_runs": stats.runs,
                        # 'wins': stats.wins,
                        # 'losses': stats.losses,
                    }
                )

        return sorted(leaders, key=lambda x: x["era"])  # Lower is better

    def leaderboard_strikeouts(self, min_innings=0) -> List[Dict[str, Any]]:
        """Get pitchers ranked by strikeouts"""
        leaders = []

        for p in self.players:
            ip = p.game_stats.pitching.ip_float
            if ip >= min_innings:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "strike_outs": p.game_stats.pitching.strike_outs,
                        "innings": ip,
                        "k_per_9": (
                            (p.game_stats.pitching.strike_outs / ip * 9)
                            if ip > 0
                            else 0
                        ),
                    }
                )

        return sorted(leaders, key=lambda x: x["strike_outs"], reverse=True)

    def leaderboard_whip(self, min_innings=5.0) -> List[Dict[str, Any]]:
        """Get pitchers ranked by WHIP (Walks + Hits per Inning Pitched)"""
        leaders = []

        for p in self.players:
            stats = p.game_stats.pitching
            innings = stats.ip_float

            if innings >= min_innings:
                # WHIP = (Walks + Hits) / Innings Pitched
                whip = (stats.walks + stats.hits) / innings if innings > 0 else 0.0

                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "whip": whip,
                        "walks": stats.walks,
                        "hits": stats.hits,
                        "innings": innings,
                    }
                )

        return sorted(leaders, key=lambda x: x["whip"])  # Lower is better

    def leaderboard_saves(self, min_innings=0) -> List[Dict[str, Any]]:
        """Get pitchers ranked by saves"""
        leaders = []

        for p in self.players:
            ip = p.game_stats.pitching.ip_float
            if ip >= min_innings:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "saves": p.game_stats.pitching.saves,
                        "innings": ip,
                    }
                )

        return sorted(leaders, key=lambda x: x["saves"], reverse=True)

    # ============ FIELDING LEADERBOARDS ============

    def leaderboard_putouts(self) -> List[Dict[str, Any]]:
        """Get players ranked by putouts"""
        leaders = []

        for p in self.players:
            leaders.append(
                {
                    "player": p,
                    "player_name": getattr(p, "name", str(p.id)),
                    "putouts": p.game_stats.fielding.putouts,
                    "assists": p.game_stats.fielding.assists,
                    "errors": p.game_stats.fielding.errors,
                }
            )

        return sorted(leaders, key=lambda x: x["putouts"], reverse=True)

    def leaderboard_assists(self) -> List[Dict[str, Any]]:
        """Get players ranked by assists"""
        leaders = []

        for p in self.players:
            leaders.append(
                {
                    "player": p,
                    "player_name": getattr(p, "name", str(p.id)),
                    "assists": p.game_stats.fielding.assists,
                    "putouts": p.game_stats.fielding.putouts,
                    "errors": p.game_stats.fielding.errors,
                }
            )

        return sorted(leaders, key=lambda x: x["assists"], reverse=True)

    def leaderboard_fielding_percentage(self, min_chances=10) -> List[Dict[str, Any]]:
        """Get players ranked by fielding percentage"""
        leaders = []

        for p in self.players:
            stats = p.game_stats.fielding
            chances = stats.putouts + stats.assists + stats.errors

            if chances >= min_chances:
                # Fielding % = (PO + A) / (PO + A + E)
                fielding_pct = (
                    (stats.putouts + stats.assists) / chances if chances > 0 else 0.0
                )

                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "fielding_pct": fielding_pct,
                        "putouts": stats.putouts,
                        "assists": stats.assists,
                        "errors": stats.errors,
                        "chances": chances,
                    }
                )

        return sorted(leaders, key=lambda x: x["fielding_pct"], reverse=True)

    # ============ UTILITY METHODS ============

    def print_leaderboard(
        self,
        title: str,
        leaders: List[Dict[str, Any]],
        stat_key: str,
        top_n: int = 10,
        format_str: str = ".3f",
    ):
        """Pretty print a leaderboard"""
        print(f"\n{'=' * 60}")
        print(f"{title:^60}")
        print(f"{'=' * 60}")

        for i, leader in enumerate(leaders[:top_n], 1):
            player_name = leader["player_name"]
            stat_value = leader[stat_key]

            if format_str:
                stat_display = f"{stat_value:{format_str}}"
            else:
                stat_display = str(stat_value)

            # Add context stats
            context = []
            if "at_bats" in leader:
                context.append(f"AB: {leader['at_bats']}")
            if "hits" in leader and stat_key != "hits":
                context.append(f"H: {leader['hits']}")
            if "innings" in leader:
                context.append(f"IP: {leader['innings']:.1f}")

            context_str = f" ({', '.join(context)})" if context else ""

            print(f"{i:2d}. {player_name:30s} {stat_display:>10s}{context_str}")
