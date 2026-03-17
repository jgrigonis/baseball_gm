# scripts/parse_leaders.py
"""
Parse top N leaders from view_leaderboards.py output.
Usage: python scripts/parse_leaders.py <N> < leaderboard_output.txt
"""

import sys
import re

SECTIONS = [
    "HOME RUN LEADERS",
    "BATTING AVERAGE LEADERS",
    "SAVE LEADERS",
    "WIN LEADERS",
    "INNINGS PITCHED LEADERS",
    "ERA LEADERS",
    "STRIKEOUT LEADERS",
]

def parse_leaders(text: str, top_n: int = 3) -> list[str]:
    seen = set()
    results = []

    for section in SECTIONS:
        idx = text.find(section)
        if idx == -1:
            continue
        chunk = text[idx:idx + 800]
        count = 0
        for line in chunk.split('\n'):
            match = re.match(r'\s+(\d+)\.\s+([A-Z][A-Z\s]+[A-Z])\s', line)
            if match and int(match.group(1)) <= top_n:
                name = match.group(2).strip()
                if name not in seen:
                    seen.add(name)
                    results.append(name)
                count += 1
                if count >= top_n:
                    break

    return results

if __name__ == "__main__":
    top_n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    text = sys.stdin.read()
    for name in parse_leaders(text, top_n):
        print(name)