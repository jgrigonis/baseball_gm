# Team uniforms

Each team gets a full uniform set, designed one team at a time. Every set uses the team's three colors from `src/team/colors.py`.

## Layout

- `docs/design/uniforms/<team>.html` is the design sheet. It holds every piece as an inline SVG, with notes, and is the source for everything else. Open it in a browser to see the whole set.
- `src/web/static/img/uniforms/<city>/` holds one standalone SVG per piece, exported from the sheet. The lettering is turned into outlines, so the files need no web fonts. They are served at `/static/img/uniforms/<city>/<piece>.svg`.
- `scripts/export_uniform_svgs.py` does the export. Each `<svg data-export="...">` in a sheet names the file or files it becomes.

```
uv run --with fonttools --with svgpathtools --with uharfbuzz \
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
| Chicago Blizzards | Done (2026-10-31) | Lake-effect winter theme. Navy slab lettering has icicles hanging from it at home and on the Lake Effect alternate. The cap has a plain C, the stirrups have a jagged wind band, and the patch is a hexagonal snowflake. |
| Mumbai Mariners | Done (2026-10-31) | Harbor theme with sign-painter lettering (Yatra One). The home and Festival script climbs at 10° over a wave. The home and away cap is teal with a cream brim and a saffron anchor. The patch shows the Gateway of India with मुंबई. |
| Singapore Merlions | Done (2026-10-31) | Lion City theme. Fish-scale sleeves on the home and National Day jerseys, and arched lettering. The caps carry the Marina Bay skyline with no letters, and the patch shows the skyline against a red sun. |
| New York Titans | Done (2026-10-31) | Art Deco Manhattan with industrial lettering (Oswald, chosen from a font study). TITANS stands on a riveted girder. The Ironworkers alternate is steel gray. The cap has a skyscraper spire, and the octagon patch has a sunburst and a NEW YORK banner. |
| Dubai Falcons | Done (2026-10-31) | Desert and falcon theme with Kufic lettering (Reem Kufi). An ivory home body was added, since none of the team colors is light enough. Falcons climbs at 12° over a gold wing, and the alternate is Oasis green. The cap has a hooded falcon head, and the patch shows the falcon over dunes with دبي. |

The other 24 teams are still to do. They aren't shown in the game yet.
