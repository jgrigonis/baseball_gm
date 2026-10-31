# Team uniforms

Each team gets a full uniform set, designed one team at a time. Every set uses the team's three colors from `src/team/colors.py`.

## Layout

- `docs/design/uniforms/<team>.html` is the design sheet. It holds every piece as an inline SVG, with notes, and is the source for everything else. Open it in a browser to see the whole set.
- `src/web/static/img/uniforms/<city>/` holds one standalone SVG per piece, exported from the sheet. The lettering is turned into outlines, so the files need no web fonts. They are served at `/static/img/uniforms/<city>/<piece>.svg`.
- `scripts/export_uniform_svgs.py` does the export. Each `<svg data-export="...">` in a sheet names the file or files it becomes.

```
uv run --with fonttools --with svgpathtools \
    python scripts/export_uniform_svgs.py docs/design/uniforms/vienna-maestros.html vienna
```

## Pieces in a set

| File | What it is |
| --- | --- |
| `jersey-home.svg` | Home jersey, front |
| `jersey-away.svg` | Away jersey, front |
| `jersey-alternate.svg` | Alternate jersey, front |
| `cap.svg` | Cap for home and away |
| `cap-alternate.svg` | Cap for the alternate jersey |
| `helmet.svg` | Batting helmet |
| `pants-home.svg`, `pants-away.svg` | Pants with belt |
| `stirrups.svg`, `stirrups-alternate.svg` | Stirrup socks |
| `patch.svg` | Sleeve patch |

## Progress

| Team | Status | Notes |
| --- | --- | --- |
| Vienna Maestros | Done (2026-10-31) | Concert-hall theme. The home and Opera Night script climbs at 26°. The bat-and-baton patch sits on the player's right sleeve. |

The other 29 teams are still to do. They aren't shown in the game yet.
