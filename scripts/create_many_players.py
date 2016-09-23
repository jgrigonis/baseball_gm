"""Create a bunch of players, print out the best players in each
skill category or position rating."""
from player.player import Player, skills
from player.__init__ import rated_positions
from scripts.create_player import create
from copy import deepcopy


players_to_create = 40
maxes = deepcopy(skills)
max_ratings = {}
for item in rated_positions:
    max_ratings[item] = 0
best_players = {}
debug = False
print(Player.header())
for x in range(players_to_create):
    player = create()
    for key in player.skills:
        if player.skills[key] > maxes[key]:
            maxes[key] = player.skills[key]
            best_players[key] = deepcopy(player)
    for key in max_ratings:
        if player.ratings[key] > max_ratings[key]:
            max_ratings[key] = player.ratings[key]
            best_players[key] = deepcopy(player)
    if debug:
        print(player.horizontal())

for key in best_players:
    if key in rated_positions:
        print(key + ' (' + str(best_players[key].ratings[key]) + ')' + ': ')
        print(best_players[key].horizontal())
    else:
        print(key + ' (' + str(best_players[key].skills[key]) + ')' + ': ')
        print(best_players[key].horizontal())
