# src/player/face.py
"""
Player faces: a small illustrated head-and-shoulders portrait, drawn as
inline SVG from simple shapes.

A face is a small set of traits (TRAITS): skin tone, face shape, eyes,
brows, nose, mouth, hair, facial hair and so on. Nothing is stored yet: a
hash of the player's id seeds random traits, so a player always gets the
same face. A face built by hand on /face_gen (routers/face_gen.py) is the
same traits as a small JSON dict. Two things come from outside the traits:

- The team. He wears its cap (crown, brim, button and logo taken from the
  team's cap.svg) and a jersey in its colors, so a trade re-dresses him. A
  free agent wears a plain gray cap.
- His age. Hair and beard gray from the early 30s at a rate that differs per
  player, and lines around the eyes and mouth deepen.

player_face(player) is a template global (src/web/utils.py).
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from markupsafe import Markup, escape

from src.team.colors import colors_for, readable_ink

UNIFORMS_DIR = (
    Path(__file__).resolve().parents[1] / "web" / "static" / "img" / "uniforms"
)
LOGO_BOXES_FILE = Path(__file__).with_name("cap_logo_boxes.json")

SKIN = (
    "#f7dcc8",
    "#efc6a6",
    "#e2b08b",
    "#cf9a6e",
    "#b57d52",
    "#99623c",
    "#7a4a2b",
    "#5c341d",
    "#43251a",
)
HAIR = (
    "#1b1512",
    "#2e1f16",
    "#3d2817",
    "#5a3920",
    "#7d522d",
    "#b48a4e",
    "#d4b273",
    "#8c3f1d",
)
IRIS = ("#3b2414", "#4a2d16", "#2a1a10", "#5b6f3a", "#3f6f9b", "#6c7d8a", "#7a5a2a")
GRAY_HAIR = "#bdb8b0"
EYE_WHITE = "#f4efe6"
BACKGROUND = "#1a3f2e"  # --bg-3

# Free agents and teams without a uniform set
PLAIN_CAP = {
    "crown": "#5a5f5c",
    "seam": "#474b49",
    "button": "#474b49",
    "brim": "#4d5250",
    "brim_edge": "#3c403e",
}


# ── Color helpers ────────────────────────────────────────────────────────────


def _rgb(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def mix(a: str, b: str, t: float) -> str:
    """The color t of the way from a to b."""
    return "#" + "".join(
        f"{max(0, min(255, round(x + (y - x) * t))):02x}"
        for x, y in zip(_rgb(a), _rgb(b))
    )


def shade(c: str, t: float) -> str:
    return mix(c, "#000000", t)


def tint(c: str, t: float) -> str:
    return mix(c, "#ffffff", t)


def _n(v: float) -> str:
    """A number for SVG: two decimals at most, no trailing zeros."""
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s == "-0" else s


# ── The team's cap ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Cap:
    crown: str
    seam: str
    button: str
    brim: str
    brim_edge: str
    logo: str = ""  # SVG markup in cap.svg coordinates, ids made unique
    logo_box: tuple[float, float, float, float] | None = None  # x, y, w, h
    code: str = ""  # Shown on the crown when there's no logo


def _attr(line: str, name: str) -> str | None:
    m = re.search(rf'\b{name}="([^"]*)"', line)
    return m.group(1) if m else None


@lru_cache(maxsize=1)
def _logo_boxes() -> dict[str, tuple[float, float, float, float]]:
    try:
        raw = json.loads(LOGO_BOXES_FILE.read_text())
    except FileNotFoundError:
        return {}
    return {k: tuple(v) for k, v in raw.items()}


@lru_cache(maxsize=64)
def cap_parts(slug: str) -> Cap | None:
    """The colors and logo of a team's cap.svg, or None without one.

    Every cap.svg has the same layout (scripts/export_uniform_svgs.py): the
    crown path starting "M40 120 Q40 34", two seams, the button circle, the
    brim path starting "M36 120", then the logo. Brim trim after the brim
    (a path starting "M40 120") isn't part of the logo.
    """
    path = UNIFORMS_DIR / slug / "cap.svg"
    if not path.exists():
        return None
    svg = path.read_text()
    lines = svg.splitlines()
    crown = next((ln for ln in lines if 'd="M40 120 Q40 34' in ln), None)
    brim_i = next((i for i, ln in enumerate(lines) if 'd="M36 120' in ln), None)
    if crown is None or brim_i is None:
        return None
    seam = next((ln for ln in lines if 'd="M122 30' in ln), "")
    button = next((ln for ln in lines if ln.strip().startswith("<circle")), "")
    brim = lines[brim_i]

    defs = re.search(r"<defs>(.*?)</defs>", svg, re.S)
    logo = "\n".join(
        ln
        for ln in lines[brim_i + 1 :]
        if "</svg>" not in ln and 'd="M40 120' not in ln
    )
    defs_markup = defs.group(1) if defs else ""
    # Two teams' caps can reuse an id (and a page can show several faces), so
    # every id gets the team's prefix.
    ids = set(re.findall(r'\bid="([^"]+)"', defs_markup + logo))
    markup = (f"<defs>{defs_markup}</defs>" if defs_markup else "") + logo
    for i in ids:
        new = f"face-{slug}-{i}"
        markup = re.sub(rf'\bid="{re.escape(i)}"', f'id="{new}"', markup)
        markup = markup.replace(f'href="#{i}"', f'href="#{new}"')
        markup = markup.replace(f"url(#{i})", f"url(#{new})")

    crown_fill = _attr(crown, "fill") or PLAIN_CAP["crown"]
    return Cap(
        crown=crown_fill,
        seam=_attr(seam, "stroke") or shade(crown_fill, 0.2),
        button=_attr(button, "fill") or shade(crown_fill, 0.2),
        brim=_attr(brim, "fill") or shade(crown_fill, 0.12),
        brim_edge=_attr(brim, "stroke") or shade(crown_fill, 0.3),
        logo=markup,
        logo_box=_logo_boxes().get(slug),
    )


def team_cap(city: str | None, mascot: str | None) -> Cap:
    """The cap a player on this team wears: the team's own cap.svg when it
    has one, otherwise its colors with its code on the front. No team (a
    free agent) gets a plain gray cap."""
    if not city or city == "—":
        return Cap(**PLAIN_CAP)
    from src.api.view_models.welcome import uniform_slug  # avoid an import cycle

    cap = cap_parts(uniform_slug(city))
    if cap and cap.logo_box:
        return cap
    c = colors_for(city, mascot or "")
    return Cap(
        crown=c.primary,
        seam=shade(c.primary, 0.2),
        button=shade(c.primary, 0.2),
        brim=shade(c.primary, 0.12),
        brim_edge=c.secondary,
        code=c.badge_text,
    )


# ── Traits ───────────────────────────────────────────────────────────────────
#
# A face is a small dict of traits (FaceTraits). A player without a stored
# face gets random traits seeded by his id; a face built by hand on /face_gen
# is the same dict, small enough to store on a row as JSON.


@dataclass(frozen=True)
class Trait:
    key: str
    label: str
    kind: str  # "range", "choice" (options are names) or "color" (options are hex) or "bool"
    lo: float = 0.0
    hi: float = 1.0
    options: tuple[str, ...] = ()
    default: float | str | bool = 0.0


MOUTHS = ("flat", "smile", "grin", "smirk")
FACIAL_HAIR = (
    "none",
    "stubble",
    "mustache",
    "goatee",
    "beard",
    "chinstrap",
    "square",
)
NOSES = ("classic", "button", "roman", "broad")

# Sideburns past this length flare forward along the jaw into lambchops.
LAMBCHOP_FROM = 12.0

# In drawing order for random faces: adding a trait at the end leaves every
# existing random face as it was.
TRAITS: tuple[Trait, ...] = (
    Trait("skin", "Skin tone", "color", options=SKIN, default=SKIN[3]),
    Trait("hair", "Hair color", "color", options=HAIR, default=HAIR[0]),
    Trait("eyes", "Eye color", "color", options=IRIS, default=IRIS[0]),
    Trait("face_width", "Face width", "range", 19, 23.5, default=21.2),
    Trait("chin", "Chin width", "range", 5, 12, default=8.5),
    Trait("face_length", "Face length", "range", 76.5, 84.5, default=80.5),
    Trait("eye_spacing", "Eye spacing", "range", 7.6, 9.6, default=8.6),
    Trait("eye_height", "Eye height", "range", 55.5, 57.5, default=56.5),
    Trait("eye_open", "Eye openness", "range", 0.5, 2.2, default=1.6),
    Trait("eye_width", "Eye width", "range", 2.7, 3.8, default=3.25),
    Trait("brow_thickness", "Brow thickness", "range", 1.1, 2.5, default=1.8),
    Trait("brow_tilt", "Brow tilt", "range", -1.4, 1.6, default=0.1),
    Trait("brow_gap", "Brow gap", "range", 3.6, 5.2, default=4.4),
    Trait("nose_width", "Nose width", "range", 2.4, 4.6, default=3.5),
    Trait("nose_length", "Nose length", "range", 5.5, 8.5, default=7.0),
    Trait("mouth_width", "Mouth width", "range", 4.5, 7, default=5.75),
    Trait("mouth", "Mouth", "choice", options=MOUTHS, default="flat"),
    Trait("lips", "Lip thickness", "range", 0.8, 1.8, default=1.3),
    Trait("facial_hair", "Facial hair", "choice", options=FACIAL_HAIR, default="none"),
    Trait("sideburns", "Sideburn length", "range", 0, 22, default=5),
    Trait("long_hair", "Long hair", "bool", default=False),
    Trait("eye_black", "Eye black", "bool", default=False),
    Trait("gray_rate", "Grays how fast", "range", 0.4, 1.4, default=0.9),
    Trait("ears", "Ear size", "range", 3.6, 5, default=4.3),
    Trait("neck", "Neck width", "range", 7, 11, default=9.0),
    Trait("mole", "Mole", "bool", default=False),
    Trait("mole_x", "Mole across", "range", -12, 12, default=6.0),
    Trait("mole_y", "Mole down", "range", 60, 72, default=64.0),
    Trait("nose", "Nose", "choice", options=NOSES, default="classic"),
    Trait("cap_height", "Cap height", "range", 0, 7, default=2.5),
    Trait("brim_curve", "Brim curve", "range", 0, 1, default=0.55),
)
TRAITS_BY_KEY = {t.key: t for t in TRAITS}

FaceTraits = dict  # trait key -> value, as in TRAITS

# How often random faces get each option, as relative weights
_HAIR_WEIGHTS = (2, 1, 1, 1, 1, 1, 1, 1)  # black is twice as common
_MOUTH_WEIGHTS = (2, 2, 1, 1)
_FACIAL_HAIR_WEIGHTS = (3, 2, 1, 1, 2, 1, 1)
_NOSE_WEIGHTS = (3, 2, 1, 2)
_ODDS = {"long_hair": 0.12, "eye_black": 0.22, "mole": 0.12}
# Random faces mostly stay in the everyday part of a range
_RANDOM_RANGE = {"eye_open": (1.0, 2.1), "cap_height": (1, 4)}


def _seed(player_id: str) -> int:
    return int.from_bytes(hashlib.sha256(str(player_id).encode()).digest()[:8], "big")


def random_traits(player_id: str) -> FaceTraits:
    """The traits of the face a player gets when none is stored: random, but
    always the same for the same id."""
    r = random.Random(_seed(player_id))
    t: FaceTraits = {}
    for trait in TRAITS:
        key = trait.key
        if key == "skin":
            t["skin"] = r.choice(SKIN)
        elif key == "hair":
            # Darker skin goes with darker hair and eyes
            dark = SKIN.index(t["skin"]) >= 5
            pool = HAIR[:3] if dark else HAIR
            t["hair"] = r.choices(pool, _HAIR_WEIGHTS[: len(pool)])[0]
        elif key == "eyes":
            dark = SKIN.index(t["skin"]) >= 5
            t["eyes"] = r.choice(IRIS[:3] if dark else IRIS)
        elif key == "mouth":
            t["mouth"] = r.choices(MOUTHS, _MOUTH_WEIGHTS)[0]
        elif key == "facial_hair":
            t["facial_hair"] = r.choices(FACIAL_HAIR, _FACIAL_HAIR_WEIGHTS)[0]
        elif key == "nose":
            t["nose"] = r.choices(NOSES, _NOSE_WEIGHTS)[0]
        elif key == "sideburns":
            # One in twenty goes full 70s
            roll, length = r.random(), r.uniform(1, 9)
            t["sideburns"] = round(r.uniform(14, 22) if roll < 0.05 else length, 2)
        elif trait.kind == "bool":
            t[key] = r.random() < _ODDS[key]
        else:
            lo, hi = _RANDOM_RANGE.get(key, (trait.lo, trait.hi))
            t[key] = round(r.uniform(lo, hi), 2)
    return t


def default_traits() -> FaceTraits:
    return {t.key: t.default for t in TRAITS}


def clean_traits(raw: dict) -> FaceTraits:
    """Traits from outside (a form, a stored row) made safe to draw: unknown
    keys dropped, numbers clamped to their range, unknown options and
    missing traits replaced by the default."""
    out = default_traits()
    for key, value in (raw or {}).items():
        trait = TRAITS_BY_KEY.get(key)
        if trait is None:
            continue
        if trait.kind == "range":
            try:
                v = float(value)
            except TypeError, ValueError:
                continue
            if v == v:  # not NaN
                out[key] = round(min(trait.hi, max(trait.lo, v)), 2)
        elif trait.kind in ("choice", "color"):
            if value in trait.options:
                out[key] = value
        else:
            out[key] = value in (True, "true", "1", "on", 1)
    return out


# ── The face ─────────────────────────────────────────────────────────────────

# The face is drawn at a standard length and stretched up and down from the
# middle by face_length, so the eyes, nose, mouth and chin all spread apart.
JAW = 80.5
STRETCH_FROM_Y = 50.0


def _bezier(p0, p1, p2, p3, s):
    u = 1 - s
    return tuple(
        u**3 * a + 3 * u * u * s * b + 3 * u * s * s * c + s**3 * d
        for a, b, c, d in zip(p0, p1, p2, p3)
    )


def _jaw_edge(w: float, chin: float, side: int):
    """Points down one side of the face, from the cheekbone to the chin:
    the same curve as the head's outline."""
    cx = 50
    p0 = (cx + side * w, 56)
    p1 = (cx + side * w, 70)
    p2 = (cx + side * chin, JAW)
    p3 = (cx, JAW + 0.5)
    return [_bezier(p0, p1, p2, p3, i / 24) for i in range(25)]


def _edge_x(w: float, chin: float, side: int, y: float) -> float:
    """Where the face's outline is at height y."""
    if y <= 56:
        return 50 + side * w
    pts = _jaw_edge(w, chin, side)
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if y0 <= y <= y1:
            return x0 + (x1 - x0) * ((y - y0) / (y1 - y0 or 1))
    return pts[-1][0]


def _sideburn(w, chin, side, top, length):
    """One sideburn: a strip down the face's edge from under the cap. Past
    LAMBCHOP_FROM it widens toward the jaw and flares onto the cheek."""
    bottom = top + length
    chop = max(0.0, length - LAMBCHOP_FROM) / (22 - LAMBCHOP_FROM)  # 0..1
    steps = 10
    outer, inner = [], []
    for i in range(steps + 1):
        y = top + length * i / steps
        x = _edge_x(w, chin, side, y)
        f = i / steps
        # A tuft at the temple, a strip down, then the lambchop's flare
        width = 2.5 + max(0.0, 0.8 - f * 5) + chop * 9 * f**1.6
        outer.append((x - side * 0.3, y))
        # The inner edge starts a little lower, so the top is slanted, not
        # a block
        inner.append((x - side * width, y + 1.4 * (1 - f) ** 4))
    # The lambchop's bottom sweeps forward toward the mouth corner
    if chop:
        bx, by = inner[-1]
        inner[-1] = (bx, by - chop * 2)
    pts = outer + inner[::-1]
    d = "M" + " L".join(f"{_n(x)} {_n(y)}" for x, y in pts) + " Z"
    return d, bottom


def face_svg(
    player_id: str,
    age: int | None,
    city: str | None,
    mascot: str | None,
    traits: FaceTraits | None = None,
) -> str:
    """The SVG markup of one player's face: his stored traits if given,
    otherwise random ones from his id."""
    t = clean_traits(traits) if traits is not None else random_traits(player_id)
    age = age or 27
    skin, hair, iris = t["skin"], t["hair"], t["eyes"]
    w = t["face_width"]  # half the face's width
    chin = t["chin"]  # half the chin's width
    stretch = 1 + (t["face_length"] - JAW) / 30
    jaw = JAW
    eye_dx = t["eye_spacing"]  # from the middle
    eye_y = t["eye_height"]
    eye_ry = t["eye_open"]
    eye_rx = t["eye_width"]
    brow_t, brow_tilt, brow_gap = t["brow_thickness"], t["brow_tilt"], t["brow_gap"]
    nose_w, nose_len, nose = t["nose_width"], t["nose_length"], t["nose"]
    mouth_w, mouth, lip_t = t["mouth_width"], t["mouth"], t["lips"]
    facial_hair = t["facial_hair"]
    long_hair, eye_black = t["long_hair"], t["eye_black"]
    gray_rate = t["gray_rate"]
    ear = t["ears"]
    neck = t["neck"]  # half the neck's width
    mole = (t["mole_x"], t["mole_y"]) if t["mole"] else None

    # Age
    gray = max(0.0, min(1.0, (age - 30) / 10 * gray_rate))
    hair = mix(hair, GRAY_HAIR, gray * 0.85)
    beard_col = mix(hair, GRAY_HAIR, min(1.0, gray * 1.15) * 0.85)
    lines = max(0.0, min(1.0, (age - 27) / 12))

    cap = team_cap(city, mascot)
    if city and city != "—":
        team = colors_for(city, mascot or "")
        jersey, collar = team.primary, team.secondary
    else:
        jersey, collar = PLAIN_CAP["crown"], "#8a908c"
    skin_sh, skin_sh2, skin_hi = shade(skin, 0.18), shade(skin, 0.32), tint(skin, 0.12)
    cx = 50
    L, R = cx - w, cx + w
    ear_y = eye_y + 2
    o: list[str] = []
    add = o.append

    # Where the cap sits: its band across the forehead (before stretching)
    band = 46.5 - t["cap_height"]

    add(
        f'<rect x="13" y="13" width="74" height="74" fill="{mix(BACKGROUND, cap.crown, 0.18)}"/>'
    )

    if long_hair:
        add(
            f'<path d="M{_n(L - 1)} 52 C{_n(L - 3)} 72 {_n(L - 1)} 86 {_n(L + 4)} 92 '
            f'L{_n(R - 4)} 92 C{_n(R + 1)} 86 {_n(R + 3)} 72 {_n(R + 1)} 52 Z" fill="{shade(hair, 0.1)}"/>'
        )

    # Shoulders, neck, V-neck collar
    add(
        f'<path d="M6 100 C8 88 20 82 36 80 L64 80 C80 82 92 88 94 100 Z" fill="{jersey}"/>'
    )
    add(
        f'<path d="M{_n(cx - neck)} 70 L{_n(cx - neck)} 82 C{_n(cx - 4)} 88 {_n(cx + 4)} 88 '
        f'{_n(cx + neck)} 82 L{_n(cx + neck)} 70 Z" fill="{skin_sh}"/>'
    )
    add(
        f'<path d="M{cx - 13} 80.5 L{cx} 92 L{cx + 13} 80.5" fill="none" stroke="{collar}" '
        f'stroke-width="2.6" stroke-linejoin="round"/>'
    )

    # Everything from here to the cap is stretched by face_length.
    add(
        f'<g transform="translate(0 {_n(STRETCH_FROM_Y)}) scale(1 {stretch:.4f}) '
        f'translate(0 {_n(-STRETCH_FROM_Y)})">'
    )

    # Ears
    for x in (L + 0.5, R - 0.5):
        add(
            f'<ellipse cx="{_n(x)}" cy="{_n(ear_y)}" rx="{_n(ear)}" ry="{_n(ear * 1.45)}" fill="{skin}"/>'
        )
    for x in (L + 0.8, R - 0.8):
        add(
            f'<ellipse cx="{_n(x)}" cy="{_n(ear_y)}" rx="{_n(ear * 0.45)}" ry="{_n(ear * 0.8)}" fill="{skin_sh}"/>'
        )

    # Head (rounded on top, for when the cap sits high), and shading down
    # the right cheek
    add(
        f'<path d="M{_n(L)} 56 L{_n(L)} 40 C{_n(L)} 26 {_n(R)} 26 {_n(R)} 40 L{_n(R)} 56 '
        f"C{_n(R)} 70 {_n(cx + chin)} {_n(jaw)} {cx} {_n(jaw + 0.5)} "
        f'C{_n(cx - chin)} {_n(jaw)} {_n(L)} 70 {_n(L)} 56 Z" fill="{skin}"/>'
    )
    add(
        f'<path d="M{_n(R)} 50 L{_n(R)} 56 C{_n(R)} 70 {_n(cx + chin)} {_n(jaw)} {cx} {_n(jaw + 0.5)} '
        f'C{_n(cx + chin + 2)} {_n(jaw - 4)} {_n(R - 3)} 70 {_n(R - 2.5)} 54 Z" fill="{skin_sh}" opacity=".45"/>'
    )

    # Sideburns, from just under the ends of the bill, so all of the length
    # shows
    if t["sideburns"] > 0:
        ends = brim_ends(
            STRETCH_FROM_Y + (band - STRETCH_FROM_Y) * stretch, t["brim_curve"]
        )
        start = STRETCH_FROM_Y + (ends - STRETCH_FROM_Y) / stretch - 0.5
        for side in (-1, 1):
            d, _ = _sideburn(w, chin, side, start, t["sideburns"])
            add(f'<path d="{d}" fill="{hair}"/>')

    # Facial hair. Young players' beards come in thinner.
    if facial_hair in ("beard", "stubble"):
        alpha = 0.28 if facial_hair == "stubble" else (0.6 if age < 22 else 0.95)
        add(
            f'<path d="M{_n(L - 0.3)} 56 C{_n(L)} 72 {_n(cx - chin - 1)} {_n(jaw + 3.5)} {cx} {_n(jaw + 3.5)} '
            f"C{_n(cx + chin + 1)} {_n(jaw + 3.5)} {_n(R)} 72 {_n(R + 0.3)} 56 "
            f'C{_n(R - 2.5)} 64 {cx + 9} 67 {cx} 66.5 C{cx - 9} 67 {_n(L + 2.5)} 64 {_n(L - 0.3)} 56 Z" '
            f'fill="{beard_col}" opacity="{_n(alpha)}"/>'
        )
    if facial_hair == "square":
        # A sharp, lined-up beard: straight cheek lines with a corner, and a
        # squared-off jaw and chin
        alpha = 0.7 if age < 22 else 0.97
        sq = max(chin + 3, 10.5)
        add(
            f'<path d="M{_n(L - 0.3)} 54 L{_n(L + 3)} 62.5 L{_n(cx - mouth_w - 2)} 66.2 '
            f"L{_n(cx + mouth_w + 2)} 66.2 L{_n(R - 3)} 62.5 L{_n(R + 0.3)} 54 "
            f"L{_n(R + 0.3)} 68 L{_n(cx + sq)} {_n(jaw + 2.5)} Q{_n(cx + sq)} {_n(jaw + 4)} {_n(cx + sq - 1.5)} {_n(jaw + 4)} "
            f"L{_n(cx - sq + 1.5)} {_n(jaw + 4)} Q{_n(cx - sq)} {_n(jaw + 4)} {_n(cx - sq)} {_n(jaw + 2.5)} "
            f'L{_n(L - 0.3)} 68 Z" fill="{beard_col}" opacity="{_n(alpha)}"/>'
        )
    if facial_hair == "chinstrap":
        add(
            f'<path d="M{_n(L - 0.3)} 56 C{_n(L)} 72 {_n(cx - chin - 1)} {_n(jaw + 3)} {cx} {_n(jaw + 3)} '
            f"C{_n(cx + chin + 1)} {_n(jaw + 3)} {_n(R)} 72 {_n(R + 0.3)} 56 L{_n(R - 2.2)} 58 "
            f"C{_n(R - 2.5)} 70 {_n(cx + chin)} {_n(jaw - 1)} {cx} {_n(jaw - 1)} "
            f'C{_n(cx - chin)} {_n(jaw - 1)} {_n(L + 2.5)} 70 {_n(L + 2.2)} 58 Z" fill="{beard_col}"/>'
        )
    if facial_hair == "goatee":
        add(
            f'<path d="M{cx - 6} 73.5 C{cx - 6} {_n(jaw + 3)} {cx + 6} {_n(jaw + 3)} {cx + 6} 73.5 '
            f'C{cx + 3} 75 {cx - 3} 75 {cx - 6} 73.5 Z" fill="{beard_col}"/>'
        )
    if facial_hair in ("mustache", "goatee", "square") or (
        facial_hair == "beard" and age >= 22
    ):
        add(
            f'<path d="M{_n(cx - mouth_w - 1.5)} 70.5 C{_n(cx - mouth_w)} 67 {cx - 2} 66.5 {cx} 67.4 '
            f"C{cx + 2} 66.5 {_n(cx + mouth_w)} 67 {_n(cx + mouth_w + 1.5)} 70.5 "
            f'C{cx + 3} 69 {cx - 3} 69 {_n(cx - mouth_w - 1.5)} 70.5 Z" fill="{beard_col}"/>'
        )

    if eye_black:
        for ex in (cx - eye_dx, cx + eye_dx):
            add(
                f'<path d="M{_n(ex - 3.5)} {_n(eye_y + 3.6)} h7 l-0.6 2.6 h-5.8 Z" fill="#141414" opacity=".88"/>'
            )

    # Eyes (iris clipped to the eye, so narrow eyes stay narrow), lids,
    # brows, and lines with age
    brow_col = mix(hair, "#000000", 0.15)
    for sgn in (-1, 1):
        ex = cx + sgn * eye_dx
        eye = f'cx="{_n(ex)}" cy="{_n(eye_y)}" rx="{_n(eye_rx)}" ry="{_n(eye_ry)}"'
        clip = "eye" + hashlib.md5(f"{eye}".encode()).hexdigest()[:8]
        add(f'<clipPath id="{clip}"><ellipse {eye}/></clipPath>')
        add(f'<ellipse {eye} fill="{EYE_WHITE}"/>')
        add(
            f'<g clip-path="url(#{clip})"><circle cx="{_n(ex + 0.2)}" cy="{_n(eye_y + 0.1)}" '
            f'r="{_n(min(1.7, eye_rx * 0.55))}" fill="{iris}"/>'
            f'<circle cx="{_n(ex + 0.2)}" cy="{_n(eye_y + 0.1)}" r="0.7" fill="#0d0907"/></g>'
        )
        add(
            f'<path d="M{_n(ex - eye_rx - 0.3)} {_n(eye_y - 0.2)} Q{_n(ex)} {_n(eye_y - eye_ry * 1.6 - 0.4)} '
            f'{_n(ex + eye_rx + 0.3)} {_n(eye_y - 0.2)}" fill="none" stroke="{skin_sh2}" stroke-width=".9"/>'
        )
        bx = ex - sgn * (brow_gap - 4.5)
        by = eye_y - 4.6
        inner, outer = by + brow_tilt, by - brow_tilt * 0.4
        y_left, y_right = (outer, inner) if sgn < 0 else (inner, outer)
        add(
            f'<path d="M{_n(bx - 4.2)} {_n(y_left)} Q{_n(bx)} {_n(by - 1.6)} {_n(bx + 4.2)} {_n(y_right)}" '
            f'fill="none" stroke="{brow_col}" stroke-width="{_n(brow_t)}" stroke-linecap="round"/>'
        )
        if lines > 0.25:
            a = min(0.75, lines)
            add(
                f'<path d="M{_n(ex + sgn * (eye_rx + 1.1))} {_n(eye_y - 0.6)} l{sgn * 1.8} -0.8 '
                f'M{_n(ex + sgn * (eye_rx + 1.1))} {_n(eye_y + 0.7)} l{_n(sgn * 1.9)} 0.6" '
                f'stroke="{skin_sh2}" stroke-width=".55" opacity="{_n(a)}"/>'
            )
            add(
                f'<path d="M{_n(ex - 2.4)} {_n(eye_y + 2.9)} Q{_n(ex)} {_n(eye_y + 4)} {_n(ex + 2.4)} {_n(eye_y + 2.9)}" '
                f'fill="none" stroke="{skin_sh2}" stroke-width=".55" opacity="{_n(a * 0.8)}"/>'
            )

    # Nose
    ny = eye_y + 1 + nose_len
    add(_nose(nose, cx, eye_y, ny, nose_w, skin, skin_sh, skin_sh2, skin_hi))
    if lines > 0.35:
        a = _n(min(0.7, lines))
        for sgn in (-1, 1):
            add(
                f'<path d="M{_n(cx + sgn * (nose_w + 1.5))} {_n(ny + 0.5)} Q{_n(cx + sgn * (mouth_w + 3))} {_n(ny + 4)} '
                f'{_n(cx + sgn * (mouth_w + 2))} {_n(ny + 8)}" fill="none" stroke="{skin_sh2}" stroke-width=".6" opacity="{a}"/>'
            )

    # Mouth
    my = 72
    lip = shade(mix(skin, "#a0453a", 0.35), 0.2)
    lw, mw = _n(lip_t), mouth_w
    if mouth == "flat":
        add(
            f'<path d="M{_n(cx - mw)} {my} Q{cx} {my + 0.6} {_n(cx + mw)} {my}" fill="none" stroke="{lip}" stroke-width="{lw}" stroke-linecap="round"/>'
        )
    elif mouth == "smile":
        add(
            f'<path d="M{_n(cx - mw)} {my - 0.8} Q{cx} {my + 2.6} {_n(cx + mw)} {my - 0.8}" fill="none" stroke="{lip}" stroke-width="{lw}" stroke-linecap="round"/>'
        )
    elif mouth == "grin":
        add(
            f'<path d="M{_n(cx - mw)} {my - 1} Q{cx} {my + 4} {_n(cx + mw)} {my - 1} Q{cx} {my + 0.8} {_n(cx - mw)} {my - 1} Z" '
            f'fill="{EYE_WHITE}" stroke="{lip}" stroke-width="{_n(lip_t * 0.8)}" stroke-linejoin="round"/>'
        )
    else:  # smirk
        add(
            f'<path d="M{_n(cx - mw)} {my + 0.4} Q{cx} {my + 1} {_n(cx + mw)} {my - 1.4}" fill="none" stroke="{lip}" stroke-width="{lw}" stroke-linecap="round"/>'
        )
    add(
        f'<path d="M{_n(cx - mw * 0.5)} {my + 2.8} Q{cx} {my + 3.6} {_n(cx + mw * 0.5)} {my + 2.8}" '
        f'fill="none" stroke="{skin_sh}" stroke-width=".8" opacity=".7"/>'
    )
    if mole:
        add(
            f'<circle cx="{_n(cx + mole[0])}" cy="{_n(mole[1])}" r=".7" fill="{skin_sh2}"/>'
        )

    add("</g>")

    # The cap isn't stretched, so its logo keeps its shape; its band goes
    # where the stretched forehead puts it.
    band_on_screen = STRETCH_FROM_Y + (band - STRETCH_FROM_Y) * stretch
    add(_cap(cap, cx, w, L, R, band_on_screen, t["brim_curve"]))

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="13 13 74 74" '
        'role="img" aria-hidden="true">' + "".join(o) + "</svg>"
    )


def _nose(style, cx, eye_y, ny, nw, skin, skin_sh, skin_sh2, skin_hi) -> str:
    """The nose: its bridge, tip and nostrils, in one of NOSES."""
    top = eye_y + 1
    stroke = f'fill="none" stroke="{skin_sh2}" stroke-width="1" stroke-linecap="round"'
    if style == "button":
        # Short and round: a small tip and two nostril dots, no bridge line
        return (
            f'<ellipse cx="{cx}" cy="{_n(ny - 1)}" rx="{_n(nw * 0.6)}" ry="{_n(1.6)}" fill="{skin_sh}" opacity=".55"/>'
            f'<circle cx="{_n(cx - nw * 0.42)}" cy="{_n(ny - 0.2)}" r=".55" fill="{skin_sh2}"/>'
            f'<circle cx="{_n(cx + nw * 0.42)}" cy="{_n(ny - 0.2)}" r=".55" fill="{skin_sh2}"/>'
            f'<ellipse cx="{_n(cx + 0.5)}" cy="{_n(ny - 1.8)}" rx=".9" ry=".55" fill="{skin_hi}" opacity=".7"/>'
        )
    if style == "roman":
        # A bump on the bridge and a tip that hooks down
        mid = (top + ny) / 2
        return (
            f'<path d="M{cx - 0.4} {_n(top)} Q{cx - 2.6} {_n(mid - 0.5)} {cx - 1.6} {_n(mid + 1)} '
            f'Q{cx - 1} {_n(ny - 1)} {cx - 0.6} {_n(ny + 0.9)}" {stroke}/>'
            f'<path d="M{_n(cx - nw)} {_n(ny - 0.2)} Q{cx - 1.5} {_n(ny + 1)} {cx - 0.6} {_n(ny + 0.9)} '
            f'Q{cx + 1} {_n(ny + 1.2)} {_n(cx + nw)} {_n(ny - 0.2)}" {stroke}/>'
        )
    if style == "broad":
        # Wide, flared nostrils
        fw = nw * 1.15
        return (
            f'<path d="M{cx - 0.6} {_n(top)} Q{cx - 1.2} {_n(ny - 3)} {cx - 1.4} {_n(ny - 1.5)}" {stroke} opacity=".8"/>'
            f'<path d="M{_n(cx - fw + 1.2)} {_n(ny - 2.6)} Q{_n(cx - fw - 0.8)} {_n(ny - 0.6)} {_n(cx - fw + 1)} {_n(ny + 0.4)}" {stroke}/>'
            f'<path d="M{_n(cx + fw - 1.2)} {_n(ny - 2.6)} Q{_n(cx + fw + 0.8)} {_n(ny - 0.6)} {_n(cx + fw - 1)} {_n(ny + 0.4)}" {stroke}/>'
            f'<path d="M{_n(cx - fw + 1)} {_n(ny + 0.4)} Q{cx} {_n(ny + 1.8)} {_n(cx + fw - 1)} {_n(ny + 0.4)}" {stroke}/>'
            f'<ellipse cx="{cx}" cy="{_n(ny - 1.6)}" rx="1.3" ry=".8" fill="{skin_hi}" opacity=".55"/>'
        )
    # classic
    return (
        f'<path d="M{cx - 0.6} {_n(top)} Q{cx - 1.4} {_n(ny - 2)} {_n(cx - nw)} {_n(ny)} '
        f'Q{cx} {_n(ny + 1.8)} {_n(cx + nw)} {_n(ny)}" {stroke}/>'
        f'<path d="M{cx + 0.8} {_n(top + 1)} Q{cx + 1.6} {_n(ny - 2)} {_n(cx + nw - 0.4)} {_n(ny - 0.6)}" '
        f'fill="none" stroke="{skin_hi}" stroke-width=".8" opacity=".6"/>'
    )


def brim_ends(band: float, curve: float) -> float:
    """How far down the bill's two ends come: a curved bill's sides bend down."""
    return band + 1.2 + curve * 8


LOGO_MAX_SCALE = 0.6  # So a small logo doesn't blow up past its cap size


def _cap(cap: Cap, cx, w, L, R, band, curve) -> str:
    """A baseball cap from the front: a low six-panel crown snug on the head,
    and a bill that comes toward you, its sides curving down by `curve`
    (0 is a flat bill)."""
    o = []
    cw = w + 3.2  # half the crown's width at the band
    height = cw * 0.86
    top = band - height
    # The bill: its ends, and the middles of its back (at the crown) and
    # front (nearest you) edges
    bw = cw + 3.4
    ends = brim_ends(band, curve)
    back_mid = band - 0.8
    depth = 8.6 - curve * 1.6
    front_mid = band + depth
    # The crown's sides come down to the bill's ends, so no forehead shows
    # between them when the bill curves down
    side_bottom = max(band + 3, ends + 0.6)
    back_c = 2 * back_mid - ends  # quadratic control points from midpoints
    front_c = 2 * front_mid - ends

    # The bill's shadow on the forehead
    o.append(
        f'<path d="M{_n(L)} {_n(ends)} Q{cx} {_n(front_c)} {_n(R)} {_n(ends)} '
        f'L{_n(R)} {_n(ends + 3.5)} Q{cx} {_n(front_c + 4.5)} {_n(L)} {_n(ends + 3.5)} Z" '
        f'fill="#000" opacity=".2"/>'
    )
    # Crown: nearly straight sides down to the temples, a low round top
    o.append(
        f'<path d="M{_n(cx - cw)} {_n(side_bottom)} C{_n(cx - cw - 0.4)} {_n(band - height * 0.62)} '
        f"{_n(cx - cw * 0.62)} {_n(top)} {cx} {_n(top)} "
        f"C{_n(cx + cw * 0.62)} {_n(top)} {_n(cx + cw + 0.4)} {_n(band - height * 0.62)} "
        f'{_n(cx + cw)} {_n(side_bottom)} Z" fill="{cap.crown}"/>'
    )
    # Panel seams: the center one and the two between front and side panels
    o.append(
        f'<path d="M{cx} {_n(top + 0.6)} L{cx} {_n(band)} '
        f"M{_n(cx - cw * 0.12)} {_n(top + 0.8)} Q{_n(cx - cw * 0.66)} {_n(top + height * 0.3)} {_n(cx - cw * 0.74)} {_n(band + 1)} "
        f'M{_n(cx + cw * 0.12)} {_n(top + 0.8)} Q{_n(cx + cw * 0.66)} {_n(top + height * 0.3)} {_n(cx + cw * 0.74)} {_n(band + 1)}" '
        f'fill="none" stroke="{cap.seam}" stroke-width=".7" opacity=".85"/>'
    )
    # Light from the left: the right side panel in shadow
    o.append(
        f'<path d="M{_n(cx + cw * 0.12)} {_n(top + 0.8)} Q{_n(cx + cw * 0.66)} {_n(top + height * 0.3)} {_n(cx + cw * 0.74)} {_n(band + 1)} '
        f"L{_n(cx + cw)} {_n(side_bottom)} C{_n(cx + cw + 0.4)} {_n(band - height * 0.62)} "
        f'{_n(cx + cw * 0.62)} {_n(top)} {cx} {_n(top)} Z" fill="#000" opacity=".14"/>'
    )
    o.append(
        f'<ellipse cx="{cx}" cy="{_n(top + 0.3)}" rx="2.4" ry="1.2" fill="{cap.button}"/>'
    )
    o.append(_cap_logo(cap, cx, top, band, cw))
    # The bill: top surface, a stitched band, and the darker front lip
    o.append(
        f'<path d="M{_n(cx - bw)} {_n(ends)} Q{cx} {_n(back_c)} {_n(cx + bw)} {_n(ends)} '
        f'Q{cx} {_n(front_c)} {_n(cx - bw)} {_n(ends)} Z" fill="{cap.brim}"/>'
    )
    for share in (0.35, 0.55):
        s_mid = back_mid + (front_mid - back_mid) * share
        o.append(
            f'<path d="M{_n(cx - bw * 0.86)} {_n(ends - 0.2)} Q{cx} {_n(2 * s_mid - ends)} {_n(cx + bw * 0.86)} {_n(ends - 0.2)}" '
            f'fill="none" stroke="{shade(cap.brim, 0.28)}" stroke-width=".35" stroke-dasharray=".9 .7" opacity=".9"/>'
        )
    o.append(
        f'<path d="M{_n(cx - bw)} {_n(ends)} Q{cx} {_n(front_c)} {_n(cx + bw)} {_n(ends)}" '
        f'fill="none" stroke="{cap.brim_edge}" stroke-width="1.1" opacity=".85"/>'
    )
    # A glint along the bill's top
    o.append(
        f'<path d="M{_n(cx - bw * 0.55)} {_n(back_mid + 1.6)} Q{_n(cx - bw * 0.2)} {_n(back_mid + 0.9)} {_n(cx + bw * 0.1)} {_n(back_mid + 1.1)}" '
        f'fill="none" stroke="#fff" stroke-width=".7" stroke-linecap="round" opacity=".18"/>'
    )
    return "".join(o)


def _cap_logo(cap: Cap, cx, top, band, cw) -> str:
    # The logo sits on the two front panels, above the bill
    area_w = cw * 1.05
    area_h = (band - top) * 0.66
    cy = top + (band - top) * 0.5
    if cap.logo and cap.logo_box:
        bx, by, bw, bh = cap.logo_box
        s = min(area_w / max(bw, 1), area_h / max(bh, 1), LOGO_MAX_SCALE)
        tx = cx - (bx + bw / 2) * s
        ty = cy - (by + bh / 2) * s
        return (
            f'<g transform="translate({_n(tx)} {_n(ty)}) scale({s:.4f})">{cap.logo}</g>'
        )
    if cap.code:
        size = min(area_h * 0.95, 9 if len(cap.code) >= 3 else 11)
        ink = readable_ink(cap.crown, cap.brim_edge)
        return (
            f'<text x="{cx}" y="{_n(cy + size * 0.36)}" text-anchor="middle" '
            f"font-family=\"'Big Shoulders Display','Arial Narrow',sans-serif\" "
            f'font-weight="900" font-size="{_n(size)}" fill="{ink}">{escape(cap.code)}</text>'
        )
    return ""


def player_face(player: dict, size: str = "lg") -> Markup:
    """A player's face for a template: the SVG in a framed box. size is a
    CSS modifier (player-face--lg)."""
    svg = face_svg(
        player.get("player_id", ""),
        player.get("age"),
        player.get("team_city"),
        player.get("team_mascot"),
    )
    return Markup('<span class="player-face player-face--{size}">{svg}</span>').format(
        size=size, svg=Markup(svg)
    )
