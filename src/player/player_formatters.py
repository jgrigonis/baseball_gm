# src/player/player_formatters.py

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.team.team_in_game import TeamInGame

CSV_FIELDS = [
    "Name",
    "PS",
    "T",
    "B",
    "CL",
    "SP",
    "PO",
    "EY",
    "CT",
    "BR",
    "BU",
    "CA",
    "IF",
    "OF",
    "AR",
    "AC",
    "ST",
    "RE",
    "GB",
    "KK",
    "ID",
]


class PlayerFormatter(object):
    @staticmethod
    def abbreviate(value):
        if value == "right":
            return "R"
        if value == "left":
            return "L"
        if value == "switch":
            return "S"
        return value


class PlayerTableFormatter:
    # Class-level constant for skill order in CSV output
    SKILL_NAMES = [
        "clutch",
        "speed",
        "power",
        "eye",
        "contact",
        "base_running",
        "bunting",
        "catching",
        "infield",
        "outfield",
        "arm",
        "accuracy",
        "stamina",
        "recovery",
        "ground_balls",
        "strikes",
    ]

    @staticmethod
    def hor_skills(player):
        """Output the player and skills as a single line."""
        output = f"{player.name:<30}"  # 30 is the longest name
        try:
            output += f"{player.record.age:>4}"
        except:
            output += f"{player.age:>4}"
        try:
            output += f"{player.position:>3}"
        except AttributeError:
            output += f"{player.record.position:>3}"
        output += f"{PlayerFormatter.abbreviate(player.throws):>2}"
        output += f"{PlayerFormatter.abbreviate(player.bats):>2}"
        for item in [
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
            output += f"{item:>3}"
        output += "  "
        return output

    @staticmethod
    def hor_ratings(player):
        output = f"{player.name:<30}"  # 30 is the longest name
        for item in [
            player.ratings["sp"],
            player.ratings["rp"],
            player.ratings["p"],
            player.ratings["c"],
            player.ratings["1b"],
            player.ratings["2b"],
            player.ratings["3b"],
            player.ratings["ss"],
            player.ratings["lf"],
            player.ratings["cf"],
            player.ratings["rf"],
        ]:
            output += f"{item:>3}"
        output += "  "
        for item in [
            player.ratings["lead_off"],
            player.ratings["contact_hitter"],
            player.ratings["power_hitter"],
            player.ratings["speed_runner"],
            player.ratings["overall_offense"],
            player.ratings["overall_player"],
        ]:
            output += f"{item:>3}"
        return output

    @staticmethod
    def csv_row(player):
        """
        Output the player and skills/ratings as a list.
        Use writerow instead of writeline with it
        """
        return PlayerFormatter._build_player_fields(player)

    @staticmethod
    def csv(player):
        """
        Output the player and skills/ratings as a single csv line.
        This is a comma separated string all on one line.
        """
        fields = PlayerFormatter._build_player_fields(player)
        return ",".join(str(field) for field in fields) + "\n"

    @staticmethod
    def horizontal_stat_header(team_name="Name"):
        """Return the stat header as a single line."""
        stat_list = [
            "G",
            "AB",
            "R",
            "H",
            "2B",
            "3B",
            "HR",
            "RBI",
            "SB",
            "CS",
            "BB",
            "SO",
            "GDP",
            "HBP",
            "SAC",
            "SAB",
            "PA",
        ]
        output = f"{team_name:<31}"  # 31 is the longest team name
        for item in stat_list:
            output += f"{item:>4}"

        for item in [
            "AVG",
            "OBP",
            "SLG",
            "OPS",
        ]:
            output += f"{item:>6}"
        output += "  "
        return output

    @staticmethod
    def horizontal_pitching_stat_header(team_name="Name"):
        """Return the pitching stat header as a single line."""
        output = f"{team_name:<31}"  # 31 is the longest name
        output += f"{'IP':>5}"
        # Original stats (width 4)
        for item in [
            "H",
            "R",
            "HR",
            "HBP",
            "BB",
            "SO",
            "2B",
            "3B",
            "PO",
            "BLK",
            "WP",
        ]:
            output += f"{item:>4}"
        # Derived stats (width 5 for decimals)
        for item in [
            "ERA",
            "WHIP",
            "K/9",
            "BB/9",
        ]:
            output += f"{item:>6}"
        output += "  "
        return output

    @staticmethod
    def horizontal_defensive_stat_header(team_name="Name"):
        """Return the pitching stat header as a single line."""
        output = f"{team_name:<31}"  # 31 is the longest name allowed
        # Original stats (width 4)
        for item in [
            "G",
            "PO",
            "A",
            "E",
            "TC",  # total chances = putouts + assists + errors
        ]:
            output += f"{item:>4}"
        # Derived stats (width 6 for decimals)
        for item in [
            " FPCT",
        ]:
            output += f"{item:>6}"
        output += "  "
        return output

    @staticmethod
    def horizontal_defensive_stats(player, stat_type="game"):
        """Output the player fielding stats on a single line."""
        if stat_type == "game":
            stats = player.game_stats
        elif stat_type == "season":
            stats = player.season_stats.stats
        elif stat_type == "career":
            stats = player.career_stats.stats
        output = f"{player.name:<31}"  # 31 is the longest name
        if stat_type == "season":
            output += f"{player.season_stats.games_played:>4}"
        elif stat_type == "career":
            output += f"{player.career_stats.career_games:>4}"
        else:
            output += f"{1:>4}"
        output += f"{stats.fielding.putouts:>4}"
        output += f"{stats.fielding.assists:>4}"
        output += f"{stats.fielding.errors:>4}"
        output += f"{stats.fielding.chances:>4}"
        formatted_fpct = f"{stats.fielding.fielding_percentage:.3f}"
        output += f"{formatted_fpct:>6}"
        return output

    @staticmethod
    def horizontal_stats(player, stat_type="game"):
        """Output the player stats on a single line."""
        if stat_type == "game":
            stats = player.game_stats
        elif stat_type == "season":
            stats = player.season_stats.stats
        elif stat_type == "career":
            stats = player.career_stats.stats
        output = f"{player.name:<31}"  # 31 is the longest name
        if stat_type == "season":
            output += f"{player.season_stats.games_played:>4}"
        elif stat_type == "career":
            output += f"{player.career_stats.career_games:>4}"
        else:
            output += f"{1:>4}"
        output += f"{stats.batting.at_bats:>4}"
        output += f"{stats.batting.runs:>4}"
        output += f"{stats.batting.hits:>4}"
        output += f"{stats.batting.doubles:>4}"
        output += f"{stats.batting.triples:>4}"
        output += f"{stats.batting.home_runs:>4}"
        output += f"{stats.batting.rbi:>4}"
        output += f"{stats.batting.sb:>4}"
        output += f"{stats.batting.cs:>4}"
        output += f"{stats.batting.walks:>4}"
        output += f"{stats.batting.strike_outs:>4}"
        output += f"{stats.batting.gdp:>4}"
        output += f"{stats.batting.hbp:>4}"
        output += f"{stats.batting.sac_flys:>4}"
        output += f"{stats.batting.sac_bunts:>4}"
        output += f"{stats.batting.plate_appearances:>4}"

        # Derived stats
        batting_average = stats.batting.batting_average
        formatted_average = f"{batting_average:.3f}"

        # Remove the leading '0' if it is present
        if formatted_average.startswith("0"):
            formatted_average = " " + formatted_average[1:]
        obp = stats.batting.obp
        formatted_obp = f"{obp:.3f}"
        if formatted_obp.startswith("0"):
            formatted_obp = " " + formatted_obp[1:]
        slugging = stats.batting.slugging
        formatted_slugging = f"{slugging:.3f}"
        if formatted_slugging.startswith("0"):
            formatted_slugging = " " + formatted_slugging[1:]
        ops = stats.batting.ops
        formatted_ops = f"{ops:.3f}"
        if formatted_ops.startswith("0"):
            formatted_ops = " " + formatted_ops[1:]
        output += f"{formatted_average:>6}"
        output += f"{formatted_obp:>6}"
        output += f"{formatted_slugging:>6}"
        output += f"{formatted_ops:>6}"

        return output

    @staticmethod
    def short_batting_stats(player):
        """Output the player stats on a single line."""
        stats = player.game_stats
        output = f"{player.name:<31}"  # 31 is the longest name

        output += f"AB: {stats.batting.at_bats} "
        output += f"R: {stats.batting.runs} "
        output += f"H: {stats.batting.hits} "
        output += f"BB: {stats.batting.walks} "
        output += f"HBP: {stats.batting.hbp} "
        output += f"SAC: {stats.batting.sac_flys} "
        output += f"SAB: {stats.batting.sac_bunts} "
        return output

    @staticmethod
    def horizontal_pitching_stats(player, stat_type="game"):
        """Output the player stats on a single line."""
        if stat_type == "game":
            stats = player.game_stats
        elif stat_type == "season":
            stats = player.season_stats.stats
        elif stat_type == "career":
            stats = player.career_stats.stats
        output = str("{:<{}} ".format(player.name, 30))  # 30 is the longest name
        output += "{:>{}}".format(stats.pitching.ip_str, 5)
        output += "{:>{}}".format(stats.pitching.hits, 4)
        output += "{:>{}}".format(stats.pitching.runs, 4)
        output += "{:>{}}".format(stats.pitching.home_runs, 4)
        output += "{:>{}}".format(stats.pitching.hb, 4)
        output += "{:>{}}".format(stats.pitching.walks, 4)
        output += "{:>{}}".format(stats.pitching.strike_outs, 4)
        output += "{:>{}}".format(stats.pitching.doubles, 4)
        output += "{:>{}}".format(stats.pitching.triples, 4)
        output += "{:>{}}".format(stats.pitching.pickoffs, 4)
        output += "{:>{}}".format(stats.pitching.balks, 4)
        output += "{:>{}}".format(stats.pitching.wild_pitches, 4)

        # Derived stats
        era = stats.pitching.era
        whip = stats.pitching.whip
        ip_float = stats.pitching.ip_float

        # K/9 (strikeouts per 9 innings)
        k_per_9 = (stats.pitching.strike_outs / ip_float * 9) if ip_float > 0 else 0.0

        # BB/9 (walks per 9 innings)
        bb_per_9 = (stats.pitching.walks / ip_float * 9) if ip_float > 0 else 0.0

        output += "{:>6.2f}".format(era)
        output += "{:>6.2f}".format(whip)
        output += "{:>6.2f}".format(k_per_9)
        output += "{:>6.2f}".format(bb_per_9)
        return output

    @staticmethod
    def legend():
        """return the legend as a string"""
        output = str("\nLegend:\n")
        output += str("---------------------------\n")
        output += str("SKILLS:\n")
        output += str("PS = position\n")
        output += str("AG = age\n")
        output += str("T  = throws\n")
        output += str("B  = bats\n")
        output += str("DU = durability\n")
        output += str("CL = clutch\n")
        output += str("SP = run speed\n")
        output += str("PO = batting power\n")
        output += str("EY = eye\n")
        output += str("CT = contact hitting\n")
        output += str("BR = base running\n")
        output += str("BU = bunting\n")
        output += str("CA = catching\n")
        output += str("IF = infield skills\n")
        output += str("OF = outfield skills\n")
        output += str("AR = throwing arm\n")
        output += str("AC = pitching accuracy\n")
        output += str("ST = pitching stamina\n")
        output += str("RE = pitching recovery\n")
        output += str("GB = pitching ground balls\n")
        output += str("KK = pitching strikes\n\n")
        output += str("POSITIONAL RATINGS:\n")
        output += str("P  = Pitcher rating\n")
        output += str("C  = Catcher rating\n")
        output += str("1B = First baseman rating\n")
        output += str("2B = Second baseman rating\n")
        output += str("3B = Third baseman rating\n")
        output += str("SS = Short stop rating\n")
        output += str("LF = Left field rating\n")
        output += str("CF = Center field rating\n")
        output += str("RF = Right field rating\n\n")
        output += str("ROLE RATINGS:\n")
        output += str("LO = Lead off hitter rating\n")
        output += str("CH = Contact hitter rating\n")
        output += str("PH = Power hitter rating\n")
        output += str("SR = Speed runner rating\n")
        output += str("OO = Overall offensive rating\n")
        output += str("OP = Overall player rating\n")
        return output

    def csv_header():
        return ",".join(CSV_FIELDS) + "\n"

    @staticmethod
    def header_skills():
        """Return the header for skills as a single line."""
        output = f"{'Name':<30}"  # 30 is the longest name
        output += f"{'Age':>4}"
        output += f"{'PS':>3}"
        output += f"{'T':>2}"
        output += f"{'B':>2}"
        for item in [
            "CL",
            "SP",
            "PO",
            "EY",
            "CT",
            "BR",
            "BU",
            "CA",
            "IF",
            "OF",
            "AR",
            "AC",
            "ST",
            "RE",
            "GB",
            "KK",
        ]:
            output += f"{item:>3}"
        output += "  "
        return output

    @staticmethod
    def header_ratings():
        """Return the header for ratings as a single line."""
        output = f"{'Name':<30}"  # 30 is the longest name
        for item in ["SP", "RP", "P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]:
            output += f"{item:>3}"
        output += "  "
        for item in ["LO", "CH", "PH", "SR", "OO", "OP"]:
            output += f"{item:>3}"
        return output

    @staticmethod
    def _build_player_fields(player):
        """Helper method to build the field list for CSV output."""
        return [
            player.name,
            player.position,
            PlayerFormatter.abbreviate(player.throws),
            PlayerFormatter.abbreviate(player.bats),
            *[player.skills[skill] for skill in PlayerFormatter.SKILL_NAMES],
            player.id,
        ]

    @staticmethod
    def lineup_card(team: "TeamInGame") -> str:
        lines = ["\n"]
        lines.append("  #  Name                     Pos  B  T")
        lines.append("  " + "-" * 38)
        for i, p in enumerate(team.lineup, 1):
            pos = (p.position).upper()
            bats = p.player.record.bats or "?"
            throws = p.player.record.throws or "?"
            lines.append(f"  {i:<3} {p.player.name:<22}  {pos:<4} {bats}  {throws}")
        return "\n".join(lines)

    @staticmethod
    def rotation_card(team: "TeamInGame") -> str:
        starters = [p for p in team.players if p.is_starter]
        lines = ["\n"]
        lines.append("  #  Name                    Throws")
        lines.append("  " + "-" * 32)
        for i, q in enumerate(starters, 1):
            throws = q.record.throws or "?"
            lines.append(f"  {i:<3} {q.name:<22}  {throws}")
        return "\n".join(lines)

    @staticmethod
    def bullpen_card(team: "TeamInGame") -> str:
        relievers = [p for p in team.players if p.bullpen_role is not None]
        # Sort by role priority
        role_order = {
            "Closer": 0,
            "Setup": 1,
            "Long": 2,
            "Middle": 3,
            "Utility": 4,
            "Specialist": 5,
        }
        relievers.sort(key=lambda p: role_order.get(p.bullpen_role, 99))
        lines = ["\n"]
        lines.append("  Role        Name                    Throws")
        lines.append("  " + "-" * 40)
        for r in relievers:
            role = r.bullpen_role or "?"
            throws = r.record.throws or "?"
            lines.append(f"  {role:<12} {r.name:<22}  {throws}")
        return "\n".join(lines)
