# src/team/team_evaluator.py

from src.player.player_evaluator import PlayerEvaluator
from src.player.player_record import PlayerRecord
from statistics import mean, stdev

class TeamEvaluator:
    """
    Evaluates team strength based on player ratings.
    
    Philosophy:
    - Star players matter more than depth
    - Different weightings for starters vs bench
    - Position-specific evaluations (you need good defense AND offense)
    """
    
    # How much each player contributes to team strength
    # Top 9 (starting lineup) weighted heavily
    # Next 6 (key bench/rotation) medium weight  
    # Rest (deep bench) light weight
    PLAYER_WEIGHTS = (
        [1.0] * 9 +      # Starters (100%)
        [0.6] * 6 +      # Key bench (60%)
        [0.3] * 10       # Deep bench (30%)
    )
    
    @staticmethod
    def evaluate_team(players: list[PlayerRecord]) -> dict:
        """
        Evaluate overall team strength.
        
        Args:
            players: List of PlayerRecord objects
            
        Returns:
            Dictionary with team ratings:
            - overall_strength: 0-100 overall team rating
            - offensive_strength: 0-100 offensive rating
            - defensive_strength: 0-100 defensive rating
            - pitching_strength: 0-100 pitching rating
            - depth_score: 0-100 how deep is the roster
            - star_power: 0-100 quality of best players
            - position_ratings: dict of ratings by position
        """
        if not players:
            return TeamEvaluator._empty_evaluation()
        
        # Rate all players
        player_ratings = [
            (player, PlayerEvaluator.rate_player(player.skills))
            for player in players
        ]
        
        # Sort by overall_player rating (best first)
        player_ratings.sort(key=lambda x: x[1]['overall_player'], reverse=True)
        
        # Calculate weighted team strength
        overall_scores = [rating['overall_player'] for _, rating in player_ratings]
        overall_strength = TeamEvaluator._weighted_average(
            overall_scores, 
            TeamEvaluator.PLAYER_WEIGHTS
        )
        
        # Offensive strength (weighted)
        offensive_scores = [rating['overall_offense'] for _, rating in player_ratings]
        offensive_strength = TeamEvaluator._weighted_average(
            offensive_scores,
            TeamEvaluator.PLAYER_WEIGHTS
        )
        
        # Defensive strength (best position rating per player)
        defensive_scores = [
            max(
                rating.get('c', 0),
                rating.get('1b', 0),
                rating.get('2b', 0),
                rating.get('ss', 0),
                rating.get('3b', 0),
                rating.get('lf', 0),
                rating.get('cf', 0),
                rating.get('rf', 0),
            )
            for _, rating in player_ratings
        ]
        defensive_strength = TeamEvaluator._weighted_average(
            defensive_scores,
            TeamEvaluator.PLAYER_WEIGHTS
        )
        
        # Pitching strength (only pitchers)
        pitching_scores = [
            rating.get('p', 0)
            for _, rating in player_ratings
        ]
        # Sort pitchers and weight top arms heavily
        pitching_scores.sort(reverse=True)
        pitching_weights = [1.0, 0.9, 0.8, 0.7, 0.6] + [0.4] * 10
        pitching_strength = TeamEvaluator._weighted_average(
            pitching_scores,
            pitching_weights
        )
        
        # Depth score (how good are the bottom players?)
        depth_score = TeamEvaluator._calculate_depth(overall_scores)
        
        # Star power (how good are the top players?)
        star_power = TeamEvaluator._calculate_star_power(overall_scores)
        
        # Position-specific ratings
        position_ratings = TeamEvaluator._evaluate_positions(player_ratings)
        
        return {
            'overall_strength': int(round(overall_strength)),
            'offensive_strength': int(round(offensive_strength)),
            'defensive_strength': int(round(defensive_strength)),
            'pitching_strength': int(round(pitching_strength)),
            'depth_score': int(round(depth_score)),
            'star_power': int(round(star_power)),
            'position_ratings': position_ratings,
            'roster_size': len(players),
        }
    
    @staticmethod
    def _weighted_average(scores: list[int], weights: list[float]) -> float:
        """Calculate weighted average, handling different list lengths."""
        if not scores:
            return 0.0
        
        # Use only as many weights as we have scores
        used_weights = weights[:len(scores)]
        
        if not used_weights:
            return mean(scores)
        
        total_weight = sum(used_weights)
        weighted_sum = sum(score * weight for score, weight in zip(scores, used_weights))
        
        return weighted_sum / total_weight if total_weight > 0 else 0.0
    
    @staticmethod
    def _calculate_depth(overall_scores: list[int]) -> float:
        """
        Depth = how good are players 10-20?
        Teams with good bench players have higher depth.
        """
        if len(overall_scores) < 10:
            return 0.0
        
        # Look at players ranked 10-20
        depth_players = overall_scores[9:20]
        return mean(depth_players) if depth_players else 0.0
    
    @staticmethod
    def _calculate_star_power(overall_scores: list[int]) -> float:
        """
        Star power = how elite are the top 5 players?
        Having multiple 80+ players gives high star power.
        """
        if not overall_scores:
            return 0.0
        
        # Top 5 players
        top_players = overall_scores[:5]
        
        # Weight the best player most
        if len(top_players) >= 5:
            weights = [2.0, 1.5, 1.2, 1.0, 0.8]
            star_power = sum(score * weight for score, weight in zip(top_players, weights))
            return star_power / sum(weights)
        else:
            return mean(top_players)
    
    @staticmethod
    def _evaluate_positions(player_ratings: list[tuple[PlayerRecord, dict]]) -> dict:
        """
        Evaluate team strength at each position.
        Returns best 2-3 players per position.
        """
        positions = ['c', '1b', '2b', 'ss', '3b', 'lf', 'cf', 'rf', 'p']
        position_ratings = {}
        
        for pos in positions:
            # Get all players' ratings for this position
            pos_scores = [
                (player, rating[pos])
                for player, rating in player_ratings
                if rating.get(pos, 0) > 0
            ]
            
            # Sort by rating at this position
            pos_scores.sort(key=lambda x: x[1], reverse=True)
            
            # Take top 2-3 players (starters + backup)
            depth = 3 if pos == 'p' else 2
            top_at_position = [score for _, score in pos_scores[:depth]]
            
            if top_at_position:
                # Weight starter more than backup
                weights = [1.0, 0.5, 0.3][:len(top_at_position)]
                position_ratings[pos] = int(round(
                    TeamEvaluator._weighted_average(top_at_position, weights)
                ))
            else:
                position_ratings[pos] = 0
        
        return position_ratings
    
    @staticmethod
    def _empty_evaluation() -> dict:
        """Return evaluation for empty roster."""
        return {
            'overall_strength': 0,
            'offensive_strength': 0,
            'defensive_strength': 0,
            'pitching_strength': 0,
            'depth_score': 0,
            'star_power': 0,
            'position_ratings': {},
            'roster_size': 0,
        }
    
    @staticmethod
    def format_evaluation(evaluation: dict) -> str:
        """Format team evaluation for display."""
        lines = []
        lines.append("TEAM EVALUATION:")
        lines.append(f"  Overall Strength:    {evaluation['overall_strength']:3d}")
        lines.append(f"  Offensive Strength:  {evaluation['offensive_strength']:3d}")
        lines.append(f"  Defensive Strength:  {evaluation['defensive_strength']:3d}")
        lines.append(f"  Pitching Strength:   {evaluation['pitching_strength']:3d}")
        lines.append(f"  Star Power:          {evaluation['star_power']:3d}")
        lines.append(f"  Depth Score:         {evaluation['depth_score']:3d}")
        lines.append(f"  Roster Size:         {evaluation['roster_size']:3d}")
        
        if evaluation['position_ratings']:
            lines.append("\nPOSITION STRENGTH:")
            for pos in ['c', '1b', '2b', 'ss', '3b', 'lf', 'cf', 'rf', 'p']:
                rating = evaluation['position_ratings'].get(pos, 0)
                lines.append(f"  {pos:3s}: {rating:3d}")
        
        return "\n".join(lines)
