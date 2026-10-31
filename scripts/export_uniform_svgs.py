"""Export a team's uniform pieces from its design sheet as standalone SVGs.

The design sheet (docs/design/uniforms/<team>.html) draws every piece as an
inline <svg data-export="name"> or, for drawings holding two pieces,
data-export="name:viewBox,name:viewBox". Each piece is written to
src/web/static/img/uniforms/<team>/<name>.svg with its lettering turned into
outlines, so the files need no web fonts and look the same in an <img> tag.

    uv run --with fonttools --with svgpathtools \\
        python scripts/export_uniform_svgs.py docs/design/uniforms/vienna-maestros.html vienna

The fonts are downloaded from Google Fonts into ~/.cache/baseball_gm/fonts the
first time.
"""

from __future__ import annotations

import html
import re
import sys
import urllib.request
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from svgpathtools import parse_path

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path.home() / ".cache" / "baseball_gm" / "fonts"
GOOGLE_CSS = (
    "https://fonts.googleapis.com/css2?family=Pinyon+Script"
    "&family=Playfair+Display:ital,wght@0,700;0,900;1,700"
)
SYSTEM_SERIF = "/usr/share/fonts/truetype/freefont/FreeSerif.ttf"  # for the 𝄞 clef
PAINT = ("fill", "stroke", "stroke-width", "transform", "opacity")


def _num(n: float) -> str:
    return f"{n:.2f}".rstrip("0").rstrip(".")


def load_fonts() -> dict[tuple[str, str, str], TTFont]:
    """(family, weight, style) -> font, downloading the Google ones once."""
    CACHE.mkdir(parents=True, exist_ok=True)
    if not list(CACHE.glob("*.ttf")):
        # An old user agent makes Google Fonts serve plain TTF files.
        req = urllib.request.Request(GOOGLE_CSS, headers={"User-Agent": "Mozilla/4.0"})
        css = urllib.request.urlopen(req).read().decode()
        for i, url in enumerate(re.findall(r"url\((https://[^)]+\.ttf)\)", css)):
            (CACHE / f"font{i}.ttf").write_bytes(urllib.request.urlopen(url).read())
    fonts = {}
    for path in [*CACHE.glob("*.ttf"), Path(SYSTEM_SERIF)]:
        if not path.exists():
            continue
        f = TTFont(path)
        family = f["name"].getDebugName(1)
        family = "serif" if path.name == Path(SYSTEM_SERIF).name else family
        family = family.replace(" Black", "")
        weight = str(f["OS/2"].usWeightClass)
        style = "italic" if f["head"].macStyle & 2 else "normal"
        fonts[(family, weight, style)] = f
    return fonts


class Outliner:
    def __init__(self, fonts):
        self.fonts = fonts

    def font(self, a: dict) -> TTFont:
        key = (
            a.get("font-family"),
            a.get("font-weight", "400"),
            a.get("font-style", "normal"),
        )
        if key not in self.fonts:
            sys.exit(f"No font for {key}; have {sorted(self.fonts)}")
        return self.fonts[key]

    @staticmethod
    def layout(f, text, size, spacing):
        """[(glyph, x, advance)] and the run's width, in user units."""
        cmap, hmtx = f.getBestCmap(), f["hmtx"]
        scale = size / f["head"].unitsPerEm
        out, x = [], 0.0
        for ch in text:
            g = cmap[ord(ch)]
            adv = hmtx[g][0] * scale
            out.append((g, x, adv))
            x += adv + spacing
        return out, x - spacing

    @staticmethod
    def glyph(f, g, size, a, b, c, d, e, ff) -> str:
        """Glyph g as path data: font units scaled to size, y flipped, then
        mapped by the affine (a b c d e f)."""
        s = size / f["head"].unitsPerEm
        glyphs = f.getGlyphSet()
        pen = SVGPathPen(glyphs, ntos=_num)
        glyphs[g].draw(TransformPen(pen, (a * s, b * s, -c * s, -d * s, e, ff)))
        return pen.getCommands()

    def text(self, attrs: dict, inner: str, guides: dict) -> str:
        f = self.font(attrs)
        size = float(attrs["font-size"])
        spacing = float(attrs.get("letter-spacing", 0))
        on_path = re.match(r"<textPath ([^>]*)>(.*)</textPath>", inner, re.S)
        parts = []
        if on_path:
            # startOffset 50% with text-anchor middle: centred on the guide.
            tp = _attrs(on_path.group(1))
            guide = parse_path(guides[tp["href"][1:]])
            run, width = self.layout(f, html.unescape(on_path.group(2)), size, spacing)
            start = guide.length() / 2 - width / 2
            for g, x, adv in run:
                t = guide.ilength(start + x + adv / 2)
                p, tan = guide.point(t), guide.unit_tangent(t)
                ca, sa = tan.real, tan.imag
                parts.append(
                    self.glyph(
                        f,
                        g,
                        size,
                        ca,
                        sa,
                        -sa,
                        ca,
                        p.real - ca * adv / 2,
                        p.imag - sa * adv / 2,
                    )
                )
        else:
            run, width = self.layout(f, html.unescape(inner), size, spacing)
            x0 = float(attrs.get("x", 0)) + float(attrs.get("dx", 0))
            y0 = float(attrs.get("y", 0)) + float(attrs.get("dy", 0))
            if attrs.get("text-anchor") == "middle":
                x0 -= width / 2
            for g, x, _ in run:
                parts.append(self.glyph(f, g, size, 1, 0, 0, 1, x0 + x, y0))
        paint = " ".join(f'{k}="{attrs[k]}"' for k in PAINT if k in attrs)
        return f'<path d="{" ".join(parts)}" {paint}/>'


def _attrs(tag: str) -> dict:
    return dict(re.findall(r'([\w:-]+)="([^"]*)"', tag))


def shared_defs(sheet: str) -> dict[str, str]:
    """The sheet's page-level <defs> (jersey outline, pinstripe patterns)."""
    block = re.search(r"<defs>(.*?)</defs>", sheet, re.S).group(1)
    defs = {}
    for m in re.finditer(
        r'(<path id="([^"]+)"[^>]*/>|<pattern id="([^"]+)".*?</pattern>)', block, re.S
    ):
        defs[m.group(2) or m.group(3)] = re.sub(r"\s+", " ", m.group(1))
    return defs


def export(svg: str, name: str, viewbox: str | None, team: str, defs, outliner) -> str:
    head = re.match(r"<svg ([^>]*)>", svg)
    attrs = _attrs(head.group(1))
    body = svg[head.end() : -len("</svg>")]
    guides = dict(re.findall(r'<path id="([^"]+)" d="([^"]+)"', body))
    body = re.sub(r'\s*<text [^>]*class="label"[^>]*>.*?</text>', "", body)
    body = re.sub(
        r"<text ([^>]*)>(.*?)</text>",
        lambda m: outliner.text(_attrs(m.group(1)), m.group(2), guides),
        body,
        flags=re.S,
    )
    body = re.sub(r'\s*<path id="[^"]+" d="[^"]+" fill="none"/>', "", body)
    body = re.sub(r"\s*<!--.*?-->", "", body)
    vb = viewbox or attrs["viewBox"]
    w, h = vb.split()[2:]
    used = [v for k, v in defs.items() if f"#{k}" in body]
    label = f"{team.replace('-', ' ').title()} {name.replace('-', ' ')}"
    out = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" width="{w}" '
        f'height="{h}" role="img" aria-label="{label}">'
    )
    if used:
        out += "\n  <defs>\n    " + "\n    ".join(used) + "\n  </defs>"
    return out + body.rstrip() + "\n</svg>\n"


def main(sheet_path: str, team: str) -> None:
    sheet = Path(sheet_path).read_text()
    out_dir = ROOT / "src" / "web" / "static" / "img" / "uniforms" / team
    out_dir.mkdir(parents=True, exist_ok=True)
    defs, outliner = shared_defs(sheet), Outliner(load_fonts())
    for m in re.finditer(r'<svg data-export="([^"]+)".*?</svg>', sheet, re.S):
        svg = m.group(0).replace(f'data-export="{m.group(1)}" ', "")
        for item in m.group(1).split(","):
            name, _, viewbox = item.partition(":")
            path = out_dir / f"{name}.svg"
            path.write_text(export(svg, name, viewbox or None, team, defs, outliner))
            print(path.relative_to(ROOT))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
