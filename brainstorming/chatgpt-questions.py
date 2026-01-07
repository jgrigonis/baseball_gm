# output += "{:>{}}".format(PlayerFormatter.abbreviate(player.bats), 2)

# Can you convert this to an fstring?


output = "{:>{}}".format("65", 4)
output2 = f"{"65":>4}"
output3 = f"{65:>4}"

print(output)
print(output2)
print(output3)

# is "   G" functionally the same as f"{"G":>4}"

if "   G" == f"{"G":>4}":
    print("yes")
print(f"{"G":>4}")


#     def look_up(self, player_id: int) -> Player | None:
#         """
#         Fetch a player
#         """
# >       self.conn.execute(
#             """
#             SELECT *
#             FROM players
#             WHERE id = ?
#             """,
#             (player_id),
#         ).fetchall()
# E       sqlite3.ProgrammingError: Incorrect number of bindings supplied. The current statement uses 1, and there are 32 supplied.
#
# Solution: missing comma

# What is league in this context? Just a name for the league?
# If all the teams are in one league.db file, does it even need a name?
# CREATE TABLE IF NOT EXISTS teams (
#     id TEXT PRIMARY KEY,
#     city TEXT NOT NULL,
#     mascot TEXT NOT NULL,
#     league TEXT
# );

# self.team_repo.add_player(team_id, player.id)

# Is this a team_player connector table?
# It is

# What does it look like?
# Go see in schema


Can you turn this into a join:

for item in [
            player.position,
            PlayerFormatter.abbreviate(player.throws),
            PlayerFormatter.abbreviate(player.bats),
            player.skills["clutch"],
            player.skills["speed"],
            player.skills["power"],
            player.skills["eye"],
            player.skills["contact"],
            player.skills["base_running"],
            player.skills["bunting"],
            player.skills["catching"],
            player.skills["infield"],
            player.skills["outfield"],
            player.skills["arm"],
            player.skills["accuracy"],
            player.skills["stamina"],
            player.skills["recovery"],
            player.skills["ground_balls"],
            player.skills["strikes"],
        ]:
            output += "{},".format(item)