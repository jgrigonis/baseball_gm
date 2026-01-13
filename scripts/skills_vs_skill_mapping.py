from src.player.skill_map import SKILL_MAP
from src.player.positions import SKILLS

for csv_key, domain_key in SKILL_MAP.items():
    print(f"{csv_key} {domain_key}")

# skills = {k: row.get(k, 0) for k in SKILLS}

for skill in SKILLS:
    print(skill)
