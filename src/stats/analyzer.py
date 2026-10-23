# src/stats/analyzer.py
from typing import Any
import logging

from src.stats import formulas


class StatsAnalyzer:
    """Analyze and rank player statistics across games"""

    def __init__(self, players):
        """
        Args:
            players: List of PlayerInGame objects with game_stats
        """
        self.players = players

    # ============ BATTING LEADERBOARDS ============

    def leaderboard_home_runs(self, min_at_bats=0) -> list[dict[str, Any]]:
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

    def leaderboard_triples(self, min_at_bats=0) -> list[dict[str, Any]]:
        """Get players ranked by triples"""
        leaders = []

        for p in self.players:
            ab = p.game_stats.batting.at_bats
            if ab >= min_at_bats:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "triples": p.game_stats.batting.triples,
                        "at_bats": ab,
                    }
                )

        return sorted(leaders, key=lambda x: x["triples"], reverse=True)

    def leaderboard_doubles(self, min_at_bats=0) -> list[dict[str, Any]]:
        """Get players ranked by doubles"""
        leaders = []

        for p in self.players:
            ab = p.game_stats.batting.at_bats
            if ab >= min_at_bats:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "doubles": p.game_stats.batting.doubles,
                        "at_bats": ab,
                    }
                )

        return sorted(leaders, key=lambda x: x["doubles"], reverse=True)

    def leaderboard_singles(self, min_at_bats=0) -> list[dict[str, Any]]:
        """Get players ranked by singles"""
        leaders = []

        for p in self.players:
            ab = p.game_stats.batting.at_bats
            if ab >= min_at_bats:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "singles": p.game_stats.batting.singles,
                        "at_bats": ab,
                    }
                )

        return sorted(leaders, key=lambda x: x["singles"], reverse=True)

    def leaderboard_rbi(self, min_at_bats=0) -> list[dict[str, Any]]:
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

    def leaderboard_runs(self, min_at_bats=0) -> list[dict[str, Any]]:
        """Get players ranked by runs"""
        leaders = []

        for p in self.players:
            ab = p.game_stats.batting.at_bats
            if ab >= min_at_bats:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "runs": p.game_stats.batting.runs,
                        "at_bats": ab,
                    }
                )

        return sorted(leaders, key=lambda x: x["runs"], reverse=True)

    def leaderboard_hbp(self, min_at_bats=0) -> list[dict[str, Any]]:
        """Get players ranked by hit by pitches"""
        leaders = []

        for p in self.players:
            ab = p.game_stats.batting.at_bats
            if ab >= min_at_bats:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "hbp": p.game_stats.batting.hbp,
                        "at_bats": ab,
                    }
                )

        return sorted(leaders, key=lambda x: x["hbp"], reverse=True)

    def leaderboard_hits(self, min_at_bats=0) -> list[dict[str, Any]]:
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

    def leaderboard_double_plays(self, min_at_bats=0) -> list[dict[str, Any]]:
        """Get players ranked by double plays"""
        leaders = []

        for p in self.players:
            ab = p.game_stats.batting.at_bats
            if ab >= min_at_bats:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "double_plays": p.game_stats.batting.gdp,
                        "at_bats": ab,
                    }
                )

        return sorted(leaders, key=lambda x: x["double_plays"], reverse=True)

    def leaderboard_sac_flys(self, min_at_bats=0) -> list[dict[str, Any]]:
        """Get players ranked by total sac_flys"""
        leaders = []

        for p in self.players:
            ab = p.game_stats.batting.at_bats
            if ab >= min_at_bats:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "sac_flys": p.game_stats.batting.sac_flys,
                        "at_bats": ab,
                    }
                )

        return sorted(leaders, key=lambda x: x["sac_flys"], reverse=True)

    def leaderboard_sac_bunts(self, min_at_bats=0) -> list[dict[str, Any]]:
        """Get players ranked by total sac_bunts"""
        leaders = []

        for p in self.players:
            ab = p.game_stats.batting.at_bats
            if ab >= min_at_bats:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "sac_bunts": p.game_stats.batting.sac_bunts,
                        "at_bats": ab,
                    }
                )

        return sorted(leaders, key=lambda x: x["sac_bunts"], reverse=True)

    def leaderboard_batting_average(self, min_at_bats=10) -> list[dict[str, Any]]:
        """Get players ranked by batting average"""
        leaders = []

        for p in self.players:
            ab = p.game_stats.batting.at_bats
            if ab >= min_at_bats:
                hits = p.game_stats.batting.hits
                avg = p.game_stats.batting.batting_average
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
    ) -> list[dict[str, Any]]:
        """Get players ranked by on-base percentage (OBP)"""
        leaders = []

        for p in self.players:
            stats = p.game_stats.batting

            # OBP = (H + BB + HBP) / (AB + BB + HBP + SF)
            denominator = stats.at_bats + stats.walks + stats.hbp + stats.sac_flys

            if denominator >= min_plate_appearances:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "obp": stats.obp,
                        "hits": stats.hits,
                        "walks": stats.walks,
                        "plate_appearances": denominator,
                    }
                )

        return sorted(leaders, key=lambda x: x["obp"], reverse=True)

    def leaderboard_slugging_percentage(self, min_at_bats=10) -> list[dict[str, Any]]:
        """Get players ranked by slugging percentage (SLG)"""
        leaders = []

        for p in self.players:
            stats = p.game_stats.batting
            ab = stats.at_bats

            if ab >= min_at_bats:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "slg": stats.slugging,
                        "total_bases": stats.total_bases,
                        "at_bats": ab,
                    }
                )

        return sorted(leaders, key=lambda x: x["slg"], reverse=True)

    def leaderboard_ops(self, min_at_bats=10) -> list[dict[str, Any]]:
        """Get players ranked by OPS (On-base Plus Slugging)"""
        leaders = []

        for p in self.players:
            stats = p.game_stats.batting
            ab = stats.at_bats

            if ab >= min_at_bats:
                obp = stats.obp
                slg = stats.slugging
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

    def leaderboard_stolen_bases(self, min_at_bats=0) -> list[dict[str, Any]]:
        """Get players ranked by stolen bases"""
        leaders = []

        for p in self.players:
            ab = p.game_stats.batting.at_bats
            if ab >= min_at_bats:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "sb": p.game_stats.batting.sb,
                        "caught_stealing": p.game_stats.batting.caught_stealing,
                        "at_bats": ab,
                    }
                )

        return sorted(leaders, key=lambda x: x["sb"], reverse=True)

    def leaderboard_caught_stealing(self, min_at_bats=0) -> list[dict[str, Any]]:
        """Get players ranked by caught stealing"""
        leaders = []

        for p in self.players:
            ab = p.game_stats.batting.at_bats
            if ab >= min_at_bats:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "sb": p.game_stats.batting.sb,
                        "cs": p.game_stats.batting.cs,
                        "at_bats": ab,
                    }
                )

        return sorted(leaders, key=lambda x: x["cs"], reverse=True)

    def leaderboard_walks(self, min_at_bats=0) -> list[dict[str, Any]]:
        """Get players ranked by walks"""
        leaders = []

        for p in self.players:
            ab = p.game_stats.batting.at_bats
            if ab >= min_at_bats:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "walks": p.game_stats.batting.walks,
                        "at_bats": ab,
                    }
                )

        return sorted(leaders, key=lambda x: x["walks"], reverse=True)

    def leaderboard_batting_strikeouts(self, min_at_bats=0) -> list[dict[str, Any]]:
        """Get batters ranked by strikeouts"""
        leaders = []

        for p in self.players:
            ab = p.game_stats.batting.at_bats
            if ab >= min_at_bats:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "strikeouts": p.game_stats.batting.strike_outs,
                        "at_bats": ab,
                    }
                )

        return sorted(leaders, key=lambda x: x["strikeouts"], reverse=True)

    def leaderboard_batting_strikeouts_per_ab(
        self, min_at_bats=0
    ) -> list[dict[str, Any]]:
        """Get batters ranked by strikeouts per at-bat"""
        leaders = []

        for p in self.players:
            ab = p.game_stats.batting.at_bats
            if ab >= min_at_bats:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "k_per_ab": (
                            p.game_stats.batting.strike_outs / ab if ab > 0 else 0.0
                        ),
                        "at_bats": ab,
                    }
                )

        return sorted(leaders, key=lambda x: x["k_per_ab"], reverse=False)

    def leaderboard_batting_at_bats_per_k(self, min_at_bats=0) -> list[dict[str, Any]]:
        """Get batters ranked by at-bats per strikeout"""
        leaders = []

        for p in self.players:
            ab = p.game_stats.batting.at_bats
            if ab >= min_at_bats:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "ab_per_k": (
                            ab / p.game_stats.batting.strike_outs
                            if p.game_stats.batting.strike_outs > 0
                            else 0.0
                        ),
                        "at_bats": ab,
                    }
                )

        return sorted(leaders, key=lambda x: x["ab_per_k"], reverse=True)

    # ============ PITCHING LEADERBOARDS ============

    def leaderboard_wins(self, min_innings=0) -> list[dict[str, Any]]:
        """Get pitchers ranked by wins"""
        leaders = []

        for p in self.players:
            ip = p.game_stats.pitching.ip_float
            if ip >= min_innings:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "wins": p.game_stats.pitching.win,
                        "losses": p.game_stats.pitching.loss,
                        "innings": ip,
                    }
                )

        return sorted(leaders, key=lambda x: x["wins"], reverse=True)

    def leaderboard_losses(self, min_innings=0) -> list[dict[str, Any]]:
        """Get pitchers ranked by losses"""
        leaders = []

        for p in self.players:
            ip = p.game_stats.pitching.ip_float
            if ip >= min_innings:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "losses": p.game_stats.pitching.loss,
                        "innings": ip,
                    }
                )

        return sorted(leaders, key=lambda x: x["losses"], reverse=True)

    def leaderboard_innings_pitched(self, min_innings=0) -> list[dict[str, Any]]:
        """Get pitchers ranked by innings pitched"""
        leaders = []

        for p in self.players:
            ip = p.game_stats.pitching.ip_float
            if ip >= min_innings:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "innings_pitched": ip,
                    }
                )

        return sorted(leaders, key=lambda x: x["innings_pitched"], reverse=True)

    def leaderboard_era(self, min_innings=5.0) -> list[dict[str, Any]]:
        """Get pitchers ranked by ERA (lower is better)"""
        leaders = []

        for p in self.players:
            stats = p.game_stats.pitching
            innings = stats.ip_float

            if innings >= min_innings:
                era = stats.era

                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "era": era,
                        "innings": innings,
                        "earned_runs": stats.earned_runs,
                        # 'wins': stats.wins,
                        # 'losses': stats.losses,
                    }
                )

        return sorted(leaders, key=lambda x: x["era"])  # Lower is better

    def leaderboard_pitch_strikeouts(self, min_innings=0) -> list[dict[str, Any]]:
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
                        "k_per_9": formulas.per_nine(
                            p.game_stats.pitching.strike_outs,
                            p.game_stats.pitching.outs,
                        ),
                    }
                )

        return sorted(leaders, key=lambda x: x["strike_outs"], reverse=True)

    def leaderboard_pitch_walks(self, min_innings=0) -> list[dict[str, Any]]:
        """Get pitchers ranked by walks"""
        leaders = []

        for p in self.players:
            ip = p.game_stats.pitching.ip_float
            if ip >= min_innings:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "walks": p.game_stats.pitching.walks,
                        "innings": ip,
                        "bb_per_9": formulas.per_nine(
                            p.game_stats.pitching.walks, p.game_stats.pitching.outs
                        ),
                    }
                )

        return sorted(leaders, key=lambda x: x["walks"], reverse=True)

    def leaderboard_whip(self, min_innings=5.0) -> list[dict[str, Any]]:
        """Get pitchers ranked by WHIP (Walks + Hits per Inning Pitched)"""
        leaders = []

        for p in self.players:
            stats = p.game_stats.pitching
            innings = stats.ip_float

            if innings >= min_innings:
                whip = stats.whip

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

    def leaderboard_saves(self, min_innings=0) -> list[dict[str, Any]]:
        """Get pitchers ranked by saves"""
        leaders = []

        for p in self.players:
            ip = p.game_stats.pitching.ip_float
            if ip >= min_innings:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "saves": p.game_stats.pitching.save,
                        "innings": ip,
                    }
                )

        return sorted(leaders, key=lambda x: x["saves"], reverse=True)

    def leaderboard_balks(self, min_innings=0) -> list[dict[str, Any]]:
        """Get pitchers ranked by balks"""
        leaders = []

        for p in self.players:
            ip = p.game_stats.pitching.ip_float
            if ip >= min_innings:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "balks": p.game_stats.pitching.balks,
                        "innings": ip,
                    }
                )

        return sorted(leaders, key=lambda x: x["balks"], reverse=True)

    def leaderboard_wild_pitches(self, min_innings=0) -> list[dict[str, Any]]:
        """Get pitchers ranked by wild pitches"""
        leaders = []

        for p in self.players:
            ip = p.game_stats.pitching.ip_float
            if ip >= min_innings:
                leaders.append(
                    {
                        "player": p,
                        "player_name": getattr(p, "name", str(p.id)),
                        "wild_pitches": p.game_stats.pitching.wild_pitches,
                        "innings": ip,
                    }
                )

        return sorted(leaders, key=lambda x: x["wild_pitches"], reverse=True)

    # ============ FIELDING LEADERBOARDS ============

    def leaderboard_putouts(self) -> list[dict[str, Any]]:
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

    def leaderboard_assists(self) -> list[dict[str, Any]]:
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

    def leaderboard_fielding_percentage(self, min_chances=10) -> list[dict[str, Any]]:
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
        leaders: list[dict[str, Any]],
        stat_key: str,
        top_n: int = 10,
        format_str: str = ".3f",
        logger: logging.Logger = None,
    ):
        """Pretty print a leaderboard"""
        lines = []
        lines.append(f"\n{'=' * 60}")
        lines.append(f"{title:^60}")
        lines.append(f"{'=' * 60}")

        # print(f"\n{'=' * 60}")
        # print(f"{title:^60}")
        # print(f"{'=' * 60}")

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
            lines.append(f"{i:2d}. {player_name:30s} {stat_display:>10s}{context_str}")

        output = "\n".join(lines)
        print(output)
        if logger:
            logger.info(output)
