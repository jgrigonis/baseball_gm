# When loading/creating a game
import sqlite3
from pathlib import Path

from src.db.repositories.games_repo import GameRepository
from src.db.repositories.pitcher_state import PitcherStateRepository
from src.util.locations import LEAGUE_FILES_DIR

conn = sqlite3.connect(Path(LEAGUE_FILES_DIR) / "league.db")

games_repo = GameRepository(conn)
pitcher_repo = PitcherStateRepository(conn)

# Get the game from database (has the date)
game_record = games_repo.get(game_id)
game_date = game_record.date  # This is the date from the games table

# Before game starts
# load pitcher states with recovery
# For every pitcher:
state = pitcher_repo.get_with_recovery(
    player_id=pitcher.id,
    game_date=game_date,  # From the game record
    recovery_rate_per_day=20.0,
)

# Set pitcher's energy
pitcher.set_energy(state.current_energy)

# ... play the game ...

# After game ends - save new state
# for every pitcher
pitcher_repo.update_after_game(
    player_id=pitcher.id,
    final_energy=pitcher.current_energy,
    pitch_count=pitcher.pitches_thrown,
    game_date=game_date,  # Same date from the game record
)
