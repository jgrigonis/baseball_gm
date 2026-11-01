# src/league/world_league.py
"""
The teams a league can play with: the World League's 30, plus a few extra
for 32-team leagues. Every new league generates fresh rosters for the teams
it picks (src/api/services/lobby_teams.team_entries).

The order matters: lobby_teams samples from these lists with seeded RNGs,
so reordering them changes which teams existing seeds pick.
"""

LEAGUE_NAME = "World League"

WORLD_TEAMS: tuple[dict, ...] = tuple(
    {"city": city, "mascot": mascot}
    for city, mascot in (
        ("London", "Lions"),
        ("New York", "Titans"),
        ("Beijing", "Dragons"),
        ("Dubai", "Falcons"),
        ("Hong Kong", "Harbor Kings"),
        ("Paris", "Musketeers"),
        ("Shanghai", "Phoenix"),
        ("Singapore", "Merlions"),
        ("Sydney", "Sharks"),
        ("Tokyo", "Samurai"),
        ("Amsterdam", "Captains"),
        ("Bangkok", "Guardians"),
        ("Chicago", "Blizzards"),
        ("Frankfurt", "Eagles"),
        ("Istanbul", "Sultans"),
        ("Jakarta", "Garudas"),
        ("Lisbon", "Navigators"),
        ("Los Angeles", "Stars"),
        ("Madrid", "Conquistadors"),
        ("Mexico City", "Aztecs"),
        ("Milan", "Serpents"),
        ("Mumbai", "Mariners"),
        ("São Paulo", "Bandeirantes"),
        ("Seoul", "White Tigers"),
        ("Toronto", "Sentinels"),
        ("Warsaw", "Hussars"),
        ("Dublin", "Shamrocks"),
        ("San Francisco", "Seals"),
        ("Vienna", "Maestros"),
        ("Buenos Aires", "Matadors"),
    )
)

# Teams past the World League's 30, for bigger leagues. There are more of them
# than a 32-team league needs, so each such league draws its own.
EXTRA_TEAMS: tuple[dict, ...] = (
    {"city": "Berlin", "mascot": "Bear"},
    {"city": "Seattle", "mascot": "Rain"},
    {"city": "Portland", "mascot": "Weird"},
)
