# src/team/colors.py
"""
Team colors: a main, second and trim color plus a short code for every World
League team (src/league/world_league.py), chosen from each team's name and
city. Pages show them as a small round badge next to the team's name
(team_badge, a template global).

A team that isn't in the table, such as a test team, gets a stable pick from FALLBACK_PALETTES so it still has
colors.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from markupsafe import Markup, escape


@dataclass(frozen=True)
class TeamColors:
    code: str
    primary: str
    secondary: str
    accent: str
    # What the round badge shows, when it isn't the code (Beijing's 北京,
    # Mexico City's CDMX).
    mark: str = ""

    @property
    def badge_text(self) -> str:
        return self.mark or self.code

    @property
    def ink(self) -> str:
        """Text color for the code on a primary-colored badge: the second
        color when it reads clearly, otherwise near-black or white."""
        return readable_ink(self.primary, self.secondary)


# (city, mascot) -> colors
TEAM_COLORS: dict[tuple[str, str], TeamColors] = {
    ("London", "Lions"): TeamColors("LON", "#A6192E", "#D4A73A", "#13294B"),
    ("New York", "Titans"): TeamColors("NY", "#0C2340", "#8E9194", "#E8E2D0"),
    ("Beijing", "Dragons"): TeamColors("BEI", "#C8261E", "#3E7DAA", "#F2B705", "北京"),
    ("Dubai", "Falcons"): TeamColors("DXB", "#B8935A", "#2F3B45", "#00843D"),
    ("Hong Kong", "Harbor Kings"): TeamColors("HK", "#E0218A", "#0B3C5D", "#F2C14E"),
    ("Paris", "Musketeers"): TeamColors("PAR", "#2B4C9B", "#C9CED6", "#B31B34"),
    ("Shanghai", "Phoenix"): TeamColors("SHA", "#E4572E", "#3B1F5C", "#F7B32B"),
    ("Singapore", "Merlions"): TeamColors("SIN", "#00A3AD", "#EF3340", "#F4EFE6"),
    ("Sydney", "Sharks"): TeamColors("SYD", "#0083B5", "#5B6770", "#F6A21E"),
    ("Tokyo", "Samurai"): TeamColors("TOK", "#1F2A60", "#D9381E", "#C9B37E"),
    ("Amsterdam", "Captains"): TeamColors("AMS", "#F36C21", "#0D2240", "#F3E9D2"),
    ("Bangkok", "Guardians"): TeamColors("BKK", "#0E6B4F", "#D4A017", "#B0233A"),
    ("Chicago", "Blizzards"): TeamColors("CHI", "#A9D6F5", "#0B2545", "#FFFFFF"),
    ("Frankfurt", "Eagles"): TeamColors("FRA", "#1A1A1A", "#C8102E", "#E2B33C"),
    ("Istanbul", "Sultans"): TeamColors("IST", "#1A3D8F", "#1B8A9C", "#D2453A"),
    ("Jakarta", "Garudas"): TeamColors("JKT", "#D89B1A", "#4A2C17", "#CE1126"),
    ("Lisbon", "Navigators"): TeamColors("LIS", "#E9DDC1", "#0E2A47", "#B22234"),
    ("Los Angeles", "Stars"): TeamColors("LA", "#2A0E5C", "#FFC93C", "#FF6F91"),
    ("Madrid", "Conquistadors"): TeamColors("MAD", "#3F4650", "#F1BF00", "#AA151B"),
    ("Mexico City", "Aztecs"): TeamColors(
        "MEX", "#00A19A", "#2B2B2B", "#E0A93B", "CDMX"
    ),
    ("Milan", "Serpents"): TeamColors("MIL", "#5A7D2A", "#C0C5C9", "#B5121B"),
    ("Mumbai", "Mariners"): TeamColors("MUM", "#F4A300", "#0B5563", "#F7F1E3"),
    ("São Paulo", "Bandeirantes"): TeamColors("SAO", "#FFCC00", "#2F6FC9", "#00A859"),
    ("Seoul", "White Tigers"): TeamColors("SEO", "#F2F0EA", "#1A1A1A", "#0047A0"),
    ("Toronto", "Sentinels"): TeamColors("TOR", "#4F7F72", "#2B2F36", "#C9A44C"),
    ("Warsaw", "Hussars"): TeamColors("WAR", "#C4122F", "#ECEAE4", "#1E1E1E"),
    ("Dublin", "Shamrocks"): TeamColors("DUB", "#169B62", "#FF883E", "#FFFFFF"),
    ("San Francisco", "Seals"): TeamColors("SF", "#7D8A93", "#C0362C", "#1F2A33"),
    ("Vienna", "Maestros"): TeamColors("VIE", "#4B1D3F", "#CBA135", "#F4EDE1"),
    ("Buenos Aires", "Matadors"): TeamColors("BA", "#6CACE4", "#F6B40E", "#B3001B"),
    # Past the World League's 30, for 32-team leagues (world_league.EXTRA_TEAMS).
    ("Berlin", "Bear"): TeamColors("BER", "#1C1C1C", "#D62828", "#F2C14E"),
    ("Seattle", "Rain"): TeamColors("SEA", "#0B3D4C", "#E8EEF0", "#2AA198"),
    ("Portland", "Weird"): TeamColors("POR", "#1B3D26", "#D7192F", "#C6D93B"),
}

# (primary, secondary, accent) for teams outside TEAM_COLORS
FALLBACK_PALETTES: tuple[tuple[str, str, str], ...] = (
    ("#3B5B4F", "#E3C770", "#F4EFE6"),
    ("#6B2D5C", "#F0A35E", "#F4EFE6"),
    ("#2F4858", "#F6AE2D", "#F4EFE6"),
    ("#8C3B2E", "#E9D8A6", "#1F2A33"),
    ("#33658A", "#F26419", "#F4EFE6"),
    ("#55505C", "#9BC1BC", "#F4EFE6"),
)


def _luminance(hex_color: str) -> float:
    n = int(hex_color.lstrip("#"), 16)
    channels = []
    for v in (n >> 16, (n >> 8) & 255, n & 255):
        c = v / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio between two hex colors (1 to 21)."""
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def readable_ink(background: str, preferred: str) -> str:
    if contrast(background, preferred) >= 3:
        return preferred
    return max(("#111111", "#FFFFFF"), key=lambda ink: contrast(background, ink))


def _code_for(city: str) -> str:
    words = city.split()
    if len(words) > 1:
        return "".join(w[0] for w in words).upper()[:3]
    return city[:3].upper()


def colors_for(city: str, mascot: str) -> TeamColors:
    known = TEAM_COLORS.get((city, mascot))
    if known:
        return known
    digest = hashlib.sha1(f"{city} {mascot}".encode()).digest()
    primary, secondary, accent = FALLBACK_PALETTES[digest[0] % len(FALLBACK_PALETTES)]
    return TeamColors(_code_for(city), primary, secondary, accent)


def team_badge(city: str, mascot: str) -> Markup:
    """A round badge with the team's code in its colors, for next to its name."""
    c = colors_for(city, mascot)
    text = c.badge_text
    # Three letters, or two full-width characters, need the smaller size.
    size = " team-badge--long" if len(text) > 2 or not text.isascii() else ""
    return Markup(
        '<span class="team-badge{size}" aria-hidden="true" '
        'style="--team-primary:{p};--team-ink:{i};--team-accent:{a};">{code}</span>'
    ).format(size=size, p=c.primary, i=c.ink, a=c.accent, code=escape(text))
