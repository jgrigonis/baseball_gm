# src/player/player_formatters.py

class PlayerFormatter(object):
    @staticmethod
    def abbreviate(value):
        if value == "right":
            return "r"
        if value == "left":
            return "l"
        if value == "switch":
            return "s"
        return value

class PlayerTableFormatter:
    @staticmethod
    def horizontal(player):
        """Output the player and skills/ratings as a single line."""
        if not player.ratings:
            player.rate_player()
        name = player.first_name + " " + player.last_name
        output = str("{:<{}} ".format(name, 30))  # 30 is the longest name
        output += "{:>{}}".format(player.position, 3)
        output += "{:>{}}".format(PlayerFormatter.abbreviate(player.throws), 2)
        output += "{:>{}}".format(PlayerFormatter.abbreviate(player.bats), 2)
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
            output += "{:>{}}".format(item, 3)
        output += "  "
        for item in [
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
            output += "{:>{}}".format(item, 3)
        output += "  "
        for item in [
            player.ratings["lead_off"],
            player.ratings["contact_hitter"],
            player.ratings["power_hitter"],
        ]:
            output += "{:>{}}".format(item, 3)
        return output
    
    @staticmethod
    def csv(player):
        """Output the player and skills/ratings as a single csv line."""
        name = player.first_name + " " + player.last_name
        output = str("{},".format(name))
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
        output += player.id
        output += "\n"
        return output

    @staticmethod
    def horizontal_stat_header(team_name="Name"):
        """Return the stat header as a single line."""
        stat_list = [
            "  G",
            " AB",
            "  R",
            "  H",
            " 2B",
            " 3B",
            " HR",
            "RBI",
            " SB",
            " CS",
            " BB",
            " SO",
            "GDP",
            "HBP",
            "SAC",
        ]
        output = str("{:<{}} ".format(team_name, 30))  # 30 is the longest name
        for item in stat_list:
            output += "{:>{}}".format(item, 4)

        for item in [
            "AVG",
            "OBP",
            "SLG",
            "OPS",
        ]:
            output += "{:>{}}".format(item, 6)
        output += "  "
        return output

    @staticmethod
    def horizontal_pitching_stat_header(team_name="Name"):
        """Return the pitching stat header as a single line."""
        output = str("{:<{}} ".format(team_name, 30))  # 30 is the longest name
        # Original stats (width 4)
        for item in [
            "   IP",
            "  H",
            "  R",
            " HR",
            "HBP",
            " BB",
            " SO",
            " 2B",
            " 3B",
            " PO",
            "BLK",
            " WP",
        ]:
            output += "{:>{}}".format(item, 4)
        # Derived stats (width 5 for decimals)
        for item in [
            " ERA",
            " WHIP",
            " K/9",
            "BB/9",
        ]:
            output += "{:>{}}".format(item, 5)
        output += "  "
        return output

    @staticmethod
    def horizontal_stats(player, stat_type="game"):
        """Output the player stats on a single line."""
        if stat_type == "game":
            stats = player.stats
        elif stat_type == "season":
            stats = player.season_stats.stats
        elif stat_type == "career":
            stats = player.career_stats.stats
        name = player.first_name + " " + player.last_name
        output = str("{:<{}} ".format(name, 30))  # 30 is the longest name
        if stat_type == "season":
            output += "{:>{}}".format(player.season_stats.games_played, 4)
        elif stat_type == "career":
            output += "{:>{}}".format(player.career_stats.career_games, 4)
        else:
            output += "{:>{}}".format(1, 4)
        output += "{:>{}}".format(stats.batting.at_bats, 4)
        output += "{:>{}}".format(stats.batting.runs, 4)
        output += "{:>{}}".format(stats.batting.hits, 4)
        output += "{:>{}}".format(stats.batting.doubles, 4)
        output += "{:>{}}".format(stats.batting.triples, 4)
        output += "{:>{}}".format(stats.batting.home_runs, 4)
        output += "{:>{}}".format(stats.batting.rbi, 4)
        output += "{:>{}}".format(stats.batting.sb, 4)
        output += "{:>{}}".format(stats.batting.cs, 4)
        output += "{:>{}}".format(stats.batting.walks, 4)
        output += "{:>{}}".format(stats.batting.strike_outs, 4)
        output += "{:>{}}".format(stats.batting.gdp, 4)
        output += "{:>{}}".format(stats.batting.hbp, 4)
        output += "{:>{}}".format(stats.batting.sac_flys, 4)

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
        output += " {}".format(formatted_average)
        output += " {}".format(formatted_obp)
        output += " {}".format(formatted_slugging)
        output += " {}".format(formatted_ops)

        return output
    
    @staticmethod
    def short_batting_stats(player):
        """Output the player stats on a single line."""
        stats = player.stats
        name = player.first_name + " " + player.last_name
        output = str("{:<{}} ".format(name, 30))  # 30 is the longest name

        output += "AB: {} ".format(stats.batting.at_bats)
        output += "R: {} ".format(stats.batting.runs)
        output += "H: {} ".format(stats.batting.hits)
        output += "BB: {} ".format(stats.batting.walks)
        output += "HBP: {} ".format(stats.batting.hbp)
        output += "SAC: {} ".format(stats.batting.sac_flys)
        return output
    
    @staticmethod
    def horizontal_pitching_stats(player, stat_type="game"):
        """Output the player stats on a single line."""
        if stat_type == "game":
            stats = player.stats
        elif stat_type == "season":
            stats = player.season_stats.stats
        elif stat_type == "career":
            stats = player.career_stats.stats
        name = player.first_name + " " + player.last_name
        output = str("{:<{}} ".format(name, 30))  # 30 is the longest name
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

        output += "{:>5.2f}".format(era)
        output += "{:>5.2f}".format(whip)
        output += "{:>5.2f}".format(k_per_9)
        output += "{:>5.2f}".format(bb_per_9)
        return output

    @staticmethod
    def legend():
        """return the legend as a string"""
        output = str("\nLegend:\n")
        output += str("---------------------------\n")
        output += str("PS = position\n")
        output += str("T  = throws\n")
        output += str("B  = bats\n")
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
        output += str("KK = pitching strikes\n")
        output += str("\nP  = Pitcher rating\n")
        output += str("C  = Catcher rating\n")
        output += str("1B = First baseman rating\n")
        output += str("2B = Second baseman rating\n")
        output += str("3B = Third baseman rating\n")
        output += str("SS = Short stop rating\n")
        output += str("LF = Left field rating\n")
        output += str("CF = Center field rating\n")
        output += str("RF = Right field rating\n")
        output += str("\nLO = Lead off hitter rating\n")
        output += str("CH = Contact hitter rating\n")
        output += str("PH = Power hitter rating\n")
        return output

    @staticmethod
    def csv_header():
        """Return the header as a single csv line."""
        output = str("{},".format("Name"))  # 30 is the longest name
        for item in [
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
        ]:
            output += "{},".format(item)
        output += "\n"
        return output

    @staticmethod
    def header():
        """Return the header as a single line."""
        output = str("{:<{}} ".format("Name", 30))  # 30 is the longest name
        output += "{:>{}}".format("PS", 3)
        output += "{:>{}}".format("T", 2)
        output += "{:>{}}".format("B", 2)
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
            output += "{:>{}}".format(item, 3)
        output += "  "
        for item in ["P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]:
            output += "{:>{}}".format(item, 3)
        output += "  "
        for item in ["LO", "CH", "PH"]:
            output += "{:>{}}".format(item, 3)
        return output
