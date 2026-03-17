# src/io/player_csv_schema.py

PLAYER_CSV_HEADER = [
    "Name",
    "Age",
    "PS",
    "T",
    "B",
    "DU",
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

# mapping from CSV column → PlayerSkills field
PLAYER_SKILL_COLUMNS = [
    "DU",
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
]

EVALUATION_CSV_HEADER = [
    "Name",
    "Age",
    "PS",
    # Defensive positions
    "C",
    "1B",
    "2B",
    "SS",
    "3B",
    "LF",
    "CF",
    "RF",
    # Pitching
    "P",
    "SP",
    "RP",
    # Offensive roles
    "LO",  # lead_off
    "CON",  # contact_hitter
    "PWR",  # power_hitter
    "SPD",  # speed_runner
    # Composites
    "OFF",  # overall_offense
    "DEF",  # defensive_value
    "OVR",  # overall_player
    "PRO",  # prospect
    "Team",
    "ID",
]

# Ordered mapping from CSV column → PlayerEvaluator rating key
EVALUATION_RATING_COLUMNS: list[tuple[str, str]] = [
    ("C", "c"),
    ("1B", "1b"),
    ("2B", "2b"),
    ("SS", "ss"),
    ("3B", "3b"),
    ("LF", "lf"),
    ("CF", "cf"),
    ("RF", "rf"),
    ("P", "p"),
    ("SP", "sp"),
    ("RP", "rp"),
    ("LO", "lead_off"),
    ("CON", "contact_hitter"),
    ("PWR", "power_hitter"),
    ("SPD", "speed_runner"),
    ("OFF", "overall_offense"),
    ("DEF", "defensive_value"),
    ("OVR", "overall_player"),
    ("PRO", "prospect"),
]
