# src/stats/check_add.py
# Check if adding stats works

from src.stats.pitching_stats import PitchingStats
p1 = PitchingStats(save=3)
p2 = PitchingStats(save=2)
p1.add(p2)
print(p1.save)  # Should be 5
