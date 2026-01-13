from src.player.skill_map import SKILL_MAP
from src.player.positions import SKILLS

domain_keys = []
for csv_key, domain_key in SKILL_MAP.items():
    domain_keys.append(domain_key)
    print(f"{csv_key} {domain_key}")

for skill in SKILLS:
    print(skill)

assert set(domain_keys) == set(SKILLS)
