# src/player/face.py
"""
Player faces: a small illustrated head-and-shoulders portrait, drawn as
inline SVG from simple shapes.

Nothing is stored. A hash of the player's id seeds the random picks, so a
player always gets the same face: skin tone, face shape, eyes, brows, nose,
mouth, hair, facial hair and so on. Two things come from outside the id:

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
# Black and dark brown are the most common, so they appear twice.
HAIR = (
    "#1b1512",
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


# ── The face ─────────────────────────────────────────────────────────────────


def _seed(player_id: str) -> int:
    return int.from_bytes(hashlib.sha256(str(player_id).encode()).digest()[:8], "big")


def face_svg(
    player_id: str, age: int | None, city: str | None, mascot: str | None
) -> str:
    """The SVG markup of one player's face."""
    r = random.Random(_seed(player_id))
    rng = r.uniform
    age = age or 27

    # Traits fixed by the id. Draw them all in a fixed order, so adding a
    # trait at the end never changes the faces players already have.
    skin_i = r.randrange(len(SKIN))
    skin = SKIN[skin_i]
    dark_skin = skin_i >= 5
    hair = r.choice(HAIR[:4] if dark_skin else HAIR)
    iris = r.choice(IRIS[:3] if dark_skin else IRIS)
    w = rng(19, 23.5)  # half the face's width
    chin = rng(5, 12)  # half the chin's width
    jaw = rng(76.5, 84.5)  # how far down the chin comes
    eye_dx = rng(7.6, 9.6)  # eye spacing from the middle
    eye_y = rng(55.5, 57.5)
    eye_ry = rng(1.4, 2.2)  # how open the eyes are
    eye_rx = rng(2.7, 3.8)  # eye width
    brow_t = rng(1.1, 2.5)
    brow_tilt = rng(-1.4, 1.6)
    brow_gap = rng(3.6, 5.2)
    nose_w = rng(2.4, 4.6)
    nose_len = rng(5.5, 8.5)
    mouth_w = rng(4.5, 7)
    mouth = r.choice(("flat", "flat", "smile", "smile", "grin", "smirk"))
    lip_t = rng(0.8, 1.8)
    facial_hair = r.choice(
        (
            "none",
            "none",
            "none",
            "stubble",
            "stubble",
            "mustache",
            "goatee",
            "beard",
            "beard",
            "chinstrap",
        )
    )
    sideburn = rng(2, 9)
    long_hair = r.random() < 0.12
    eye_black = r.random() < 0.22
    gray_rate = rng(0.4, 1.4)  # how fast he grays
    ear = rng(3.6, 5)
    neck = rng(7, 11)  # half the neck's width
    mole = (rng(-12, 12), rng(60, 72)) if r.random() < 0.12 else None

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

    # Ears
    for x in (L + 0.5, R - 0.5):
        add(
            f'<ellipse cx="{_n(x)}" cy="{_n(ear_y)}" rx="{_n(ear)}" ry="{_n(ear * 1.45)}" fill="{skin}"/>'
        )
    for x in (L + 0.8, R - 0.8):
        add(
            f'<ellipse cx="{_n(x)}" cy="{_n(ear_y)}" rx="{_n(ear * 0.45)}" ry="{_n(ear * 0.8)}" fill="{skin_sh}"/>'
        )

    # Head, and shading down the right cheek
    add(
        f'<path d="M{_n(L)} 38 L{_n(L)} 56 C{_n(L)} 70 {_n(cx - chin)} {_n(jaw)} {cx} {_n(jaw + 0.5)} '
        f'C{_n(cx + chin)} {_n(jaw)} {_n(R)} 70 {_n(R)} 56 L{_n(R)} 38 Z" fill="{skin}"/>'
    )
    add(
        f'<path d="M{_n(R)} 50 L{_n(R)} 56 C{_n(R)} 70 {_n(cx + chin)} {_n(jaw)} {cx} {_n(jaw + 0.5)} '
        f'C{_n(cx + chin + 2)} {_n(jaw - 4)} {_n(R - 3)} 70 {_n(R - 2.5)} 54 Z" fill="{skin_sh}" opacity=".45"/>'
    )

    # Sideburns
    add(
        f'<path d="M{_n(L)} 46 L{_n(L + 2.6)} 46 L{_n(L + 2.2)} {_n(46 + sideburn)} L{_n(L)} {_n(47 + sideburn)} Z" fill="{hair}"/>'
    )
    add(
        f'<path d="M{_n(R)} 46 L{_n(R - 2.6)} 46 L{_n(R - 2.2)} {_n(46 + sideburn)} L{_n(R)} {_n(47 + sideburn)} Z" fill="{hair}"/>'
    )

    # Facial hair. Young players' beards come in thinner.
    if facial_hair in ("beard", "stubble"):
        alpha = 0.28 if facial_hair == "stubble" else (0.6 if age < 22 else 0.95)
        add(
            f'<path d="M{_n(L - 0.3)} 56 C{_n(L)} 72 {_n(cx - chin - 1)} {_n(jaw + 3.5)} {cx} {_n(jaw + 3.5)} '
            f"C{_n(cx + chin + 1)} {_n(jaw + 3.5)} {_n(R)} 72 {_n(R + 0.3)} 56 "
            f'C{_n(R - 2.5)} 64 {cx + 9} 67 {cx} 66.5 C{cx - 9} 67 {_n(L + 2.5)} 64 {_n(L - 0.3)} 56 Z" '
            f'fill="{beard_col}" opacity="{_n(alpha)}"/>'
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
    if facial_hair in ("mustache", "goatee") or (facial_hair == "beard" and age >= 22):
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

    # Eyes, lids, brows, and lines with age
    brow_col = mix(hair, "#000000", 0.15)
    for sgn in (-1, 1):
        ex = cx + sgn * eye_dx
        add(
            f'<ellipse cx="{_n(ex)}" cy="{_n(eye_y)}" rx="{_n(eye_rx)}" ry="{_n(eye_ry)}" fill="{EYE_WHITE}"/>'
        )
        add(
            f'<circle cx="{_n(ex + 0.2)}" cy="{_n(eye_y + 0.1)}" r="{_n(min(1.7, eye_ry, eye_rx * 0.55))}" fill="{iris}"/>'
        )
        add(
            f'<circle cx="{_n(ex + 0.2)}" cy="{_n(eye_y + 0.1)}" r="0.7" fill="#0d0907"/>'
        )
        add(
            f'<path d="M{_n(ex - eye_rx - 0.3)} {_n(eye_y - 0.2)} Q{_n(ex)} {_n(eye_y - eye_ry - 1.6)} '
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
    add(
        f'<path d="M{cx - 0.6} {_n(eye_y + 1)} Q{cx - 1.4} {_n(ny - 2)} {_n(cx - nose_w)} {_n(ny)} '
        f'Q{cx} {_n(ny + 1.8)} {_n(cx + nose_w)} {_n(ny)}" fill="none" stroke="{skin_sh2}" '
        f'stroke-width="1" stroke-linecap="round"/>'
    )
    add(
        f'<path d="M{cx + 0.8} {_n(eye_y + 2)} Q{cx + 1.6} {_n(ny - 2)} {_n(cx + nose_w - 0.4)} {_n(ny - 0.6)}" '
        f'fill="none" stroke="{skin_hi}" stroke-width=".8" opacity=".6"/>'
    )
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

    # The cap: brim shadow on the forehead, crown, seams, button, logo, brim
    add(
        f'<path d="M{_n(L)} 44 Q{cx} 41 {_n(R)} 44 L{_n(R)} 50 Q{cx} 47.5 {_n(L)} 50 Z" fill="#000" opacity=".22"/>'
    )
    cw = w + 4
    add(
        f'<path d="M{_n(cx - cw)} 46 C{_n(cx - cw)} 25 {_n(cx - cw * 0.55)} 15.5 {cx} 15.5 '
        f'C{_n(cx + cw * 0.55)} 15.5 {_n(cx + cw)} 25 {_n(cx + cw)} 46 Z" fill="{cap.crown}"/>'
    )
    add(
        f'<path d="M{cx} 16 L{cx} 45 M{_n(cx - cw * 0.55)} 19.5 Q{_n(cx - cw * 0.7)} 32 {_n(cx - cw * 0.62)} 45 '
        f'M{_n(cx + cw * 0.55)} 19.5 Q{_n(cx + cw * 0.7)} 32 {_n(cx + cw * 0.62)} 45" fill="none" '
        f'stroke="{cap.seam}" stroke-width=".7" opacity=".9"/>'
    )
    add(
        f'<path d="M{_n(cx + cw * 0.3)} 19 C{_n(cx + cw * 0.75)} 22 {_n(cx + cw)} 32 {_n(cx + cw)} 46 '
        f'L{_n(cx + cw * 0.62)} 46 Q{_n(cx + cw * 0.7)} 30 {_n(cx + cw * 0.3)} 19 Z" fill="#000" opacity=".12"/>'
    )
    add(f'<ellipse cx="{cx}" cy="16" rx="2.6" ry="1.4" fill="{cap.button}"/>')
    add(_cap_logo(cap, cx))
    add(
        f'<path d="M{_n(cx - cw - 2)} 45.5 Q{cx} 39.5 {_n(cx + cw + 2)} 45.5 Q{_n(cx + cw + 1)} 51 {_n(cx + cw - 5)} 51.5 '
        f'Q{cx} 47.5 {_n(cx - cw + 5)} 51.5 Q{_n(cx - cw - 1)} 51 {_n(cx - cw - 2)} 45.5 Z" fill="{cap.brim}"/>'
    )
    add(
        f'<path d="M{_n(cx - cw + 5)} 51.5 Q{cx} 47.5 {_n(cx + cw - 5)} 51.5" fill="none" '
        f'stroke="{cap.brim_edge}" stroke-width=".9" opacity=".8"/>'
    )

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="13 13 74 74" '
        'role="img" aria-hidden="true">' + "".join(o) + "</svg>"
    )


# The front of the crown where the logo goes, in face coordinates.
LOGO_W, LOGO_H, LOGO_CY = 26.0, 20.0, 32.0
LOGO_MAX_SCALE = 0.6  # So a small logo doesn't blow up past its cap size


def _cap_logo(cap: Cap, cx: float) -> str:
    if cap.logo and cap.logo_box:
        bx, by, bw, bh = cap.logo_box
        s = min(LOGO_W / max(bw, 1), LOGO_H / max(bh, 1), LOGO_MAX_SCALE)
        tx = cx - (bx + bw / 2) * s
        ty = LOGO_CY - (by + bh / 2) * s
        return (
            f'<g transform="translate({_n(tx)} {_n(ty)}) scale({s:.4f})">{cap.logo}</g>'
        )
    if cap.code:
        size = 9.5 if len(cap.code) >= 3 else 12
        ink = readable_ink(cap.crown, cap.brim_edge)
        return (
            f'<text x="{cx}" y="38.5" text-anchor="middle" '
            f"font-family=\"'Big Shoulders Display','Arial Narrow',sans-serif\" "
            f'font-weight="900" font-size="{size}" fill="{ink}">{escape(cap.code)}</text>'
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
