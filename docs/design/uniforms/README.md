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
| Madrid Conquistadors | Done (2026-10-31) | Iron, gold and red, with a cream home body. "Conquistadors" is arched in Pirata One blackletter, and MADRID is set in Cinzel Roman capitals. The alternate is Rojigualda red and gold. The caps carry a gold morion, the stirrups a red-gold-red flag band, and the patch is a shield with crossed Toledo swords. |
| Toronto Sentinels | Done (2026-10-31) | Pine green, charcoal and gold, with a cream home body. "Sentinels" is a rising Yellowtail script, and TORONTO and the numbers are in Alfa Slab One. The alternate is the charcoal Night Watch. The CN Tower is on the caps, helmet and stirrups, and the patch shows the tower over Lake Ontario. |
| Warsaw Hussars | Done (2026-10-31) | The Polish flag's white and red with black trim, and all the lettering in Playfair Display Black. Home says HUSSARS, the red road jersey says WARSAW, and the black alternate says WARSZAWA. The caps carry the winged hussar's feathered wing, and the patch is a red shield with the wing over crossed lances. |
| Istanbul Sultans | Done (2026-10-31) | Iznik tiles: cobalt, turquoise and coral with an ivory home body. Lettering is Lalezar. Home says Sultans, the cobalt road jersey says İSTANBUL, and the alternate is turquoise Iznik. Sleeves and stirrups end in a coral-dotted tile band, the caps carry an Ottoman tulip, and the patch is a tile roundel with a skyline of domes and minarets. |
| Frankfurt Eagles | Done (2026-10-31) | Neues Frankfurt modernism in black, red and gold with a white home body. The lettering is Jost, set straight across over a tricolor bar: EAGLES at home, FRANKFURT on the black road jersey, and a red Römer alternate. The caps carry a geometric eagle, and the patch is a Bauhaus square with the eagle on a red disc. |
| Dublin Shamrocks | Done (2026-10-31) | The tricolour in Uncial Antiqua lettering. Home is white with green Shamrocks, the road jersey is green with white Dublin, and the orange alternate is Samhain. The caps carry a shamrock, and the roundel patch reads Dublin over Baile Átha Cliath. |
| Los Angeles Stars | Done (2026-10-31) | Hollywood after dark in purple, gold and pink. The jerseys use a rising Pacifico script with Bungee numbers: Stars on white at home, Los Angeles in gold on purple on the road, and a pink Sunset alternate. The caps carry a gold star, the stirrups have a band that fades gold to pink, and the patch is a striped retro sunset with palms. |
| Beijing Dragons | Done (2026-10-31) | Imperial red and gold with Temple of Heaven blue and a cream home body. DRAGONS is arched in Archivo Black on the home and red Imperial jerseys, and the blue road jersey carries 北京 in Ma Shan Zheng brush calligraphy. The caps carry a gold dragon, and the patch is the Temple of Heaven. |
| Amsterdam Captains | Done (2026-10-31) | Golden Age harbor in orange, navy and cream, lettered in Alegreya SC Black. Captains at home, AMSTERDAM on the navy road jersey, and an Oranje alternate. The caps carry a ship's wheel, the stirrups carry the city's XXX crosses, and the patch is a row of canal-house gables. |
| Lisbon Navigators | Done (2026-10-31) | Age of Discovery in sand, navy and red, lettered in Fraunces Black. Navigators on sand at home, LISBOA on the navy road jersey, and a red Caravela alternate. The caps carry a compass rose, the stirrups a sand band with the flared sail cross, and the patch is a caravel under sail. |
| Paris Musketeers | Done (2026-10-31) | The musketeers' cassock blue and silver with red trim, lettered in Abril Fatface. Musketeers on white at home, PARIS on the silver road jersey, and a blue Cassock alternate. The caps carry a fleur-de-lis, and the patch crosses three rapiers over TOUS POUR UN. |
| Hong Kong Harbor Kings | Done (2026-10-31) | Neon magenta, harbor navy and gold, lettered in the rounded sign face Righteous. KINGS under a gold crown on white at home, a big neon HK on the navy road jersey, and a magenta Neon alternate. The caps carry a gold HK, and the patch sails a junk with magenta sails past the skyline, with 香港. |
| Seoul White Tigers | Done (2026-10-31) | Hanji cream, ink black and taegeuk blue, lettered in Black Han Sans. TIGERS on cream at home, SEOUL on the blue road jersey, and a black Baekho alternate with 서울 in Hangul and tiger-striped sleeves. The caps carry the white tiger's face, the stirrups wear its stripes, and the patch sets the tiger in front of Bukhansan. |
| Buenos Aires Matadors | Done (2026-10-31) | Celeste, sun gold and red, lettered in the bullring-poster wood type Rye. MATADORS on white pinstripes at home, a big gold BA on the celeste road jersey, and a red suit-of-lights alternate with gold embroidery. The caps carry a gold BA, and the patch crosses the cape and sword under a gold sun. |
| Tokyo Samurai | Done (2026-10-31) | Hakama indigo, shrine-gate vermilion and armor gold, lettered in Dela Gothic One. SAMURAI on white at home, TOKYO on the indigo road jersey, and a vermilion Torii alternate with a big 侍. The caps carry a gold kabuto with its horned crest, and the patch crosses two katana over the red sun, with 東京. |
| Mexico City Aztecs | Done (2026-10-31) | Jade, obsidian and gold, lettered in the blocky sign face Bungee. AZTECS on white at home, CDMX on the obsidian road jersey, and a jade alternate with a gold stepped-fret band across the chest. The cap and helmet carry CDMX, the jade alternate cap an eight-rayed gold sun, and the patch shows the Templo Mayor at sunrise. |
| Sydney Sharks | Done (2026-10-31) | Harbour blue, shark slate and sunset orange, lettered in the surf-poster face Bowlby One. SHARKS on white at home, SYDNEY on the slate road jersey, and a blue Harbour alternate with a white wave across the hem. The caps carry a fin cutting a wave, and the patch puts the fin under the Harbour Bridge at sunset. |
| Jakarta Garudas | Done (2026-10-31) | Temple gold, soga batik brown and merah red, lettered in Lilita One. GARUDAS on white at home, JAKARTA on the red road jersey, and a brown Batik alternate with a gold parang band across the hem. The caps carry JKT, and the patch spreads a gold garuda's wings over a red sun. |
| Milan Serpents | Done (2026-10-31) | Olive, silver and red, lettered in Bodoni Moda. SERPENTS on white at home, MILANO on the silver road jersey, and an olive Biscione alternate with silver serpent scales across the hem. The caps carry a Bodoni S with fangs, and the patch rears a black crowned cobra in front of the Duomo's spires. |
| London Lions | Done (2026-10-31) | Pillar-box red, gold and City navy, lettered in the Victorian slab Ultra. LIONS on white at home, LONDON on the red road jersey, and a navy chalk-stripe alternate like a Savile Row suit. The caps carry a gold slab L, and the patch puts Tower Bridge under a gold crown. |
| São Paulo Bandeirantes | Done (2026-10-31) | Canary yellow, sky blue and mata green, lettered in the condensed poster face Passion One. BANDEIRANTES on white at home, SÃO PAULO on the blue road jersey, and an all-yellow alternate with a big SP. The caps and helmet carry a spaced-out SP, and the patch plants a bandeira flag on a green ridge under the sun. |
| Shanghai Phoenix | Done (2026-10-31) | Phoenix orange, Bund gold and night purple, lettered in the wide poster face Poller One. PHOENIX on white at home, SHANGHAI on the purple road jersey, and a gold alternate with a big S and H either side of the placket. The caps and helmet carry a phoenix with raised flame wings, and the patch puts the Oriental Pearl Tower in front of its wings. |

The other 2 teams are still to do. They aren't shown in the game yet.
