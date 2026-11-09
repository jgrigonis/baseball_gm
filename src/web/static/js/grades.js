// src/web/static/grades.js

// Scouting grade ordering — best to worst, used for client-side sorting.
const GRADE_ORDER = ['A+','A','A-','B+','B','B-','C+','C','C-','D+','D','D-','F','?'];

// Returns a sortable integer for a grade string (lower = better).
// Unknown or missing grades sort to the bottom.
function gradeVal(g) {
  const i = GRADE_ORDER.indexOf(g || '?');
  return i === -1 ? 99 : i;
}

// Returns a CSS class string for coloring a grade badge.
function gradeClass(g) {
  return 'grade grade-' + (g || '?').replace('+', '-plus').replace(/-(?!plus)/g, '-minus');
}

function playerGradesHtml(p) {
  const pairs = p.player_type === 'pitcher'
    ? [['STF',p.stuff],['CTL',p.control],['STA',p.stamina],['REC',p.recovery],['GB',p.ground_balls]]
    : [['CON',p.contact],['POW',p.power],['EYE',p.eye],['SPD',p.speed],
       ['ARM',p.arm],[p.best_def_label||'DEF',p.best_def_grade]];
  return pairs.filter(([,v])=>v)
    .map(([k,v])=>`<span><span class="gl">${k}</span><span class="${gradeClass(v)}">${v}</span></span>`)
    .join('');
}

// A small face for a player row (face_url in src/player/face.py); clicking it
// opens the player panel, where the face can be seen bigger. Rows that open
// the panel on any click themselves pass clickable=false.
function faceImgHtml(p, clickable = true) {
  if (!p.face_url) return '<span></span>';
  const click = clickable ? ` onclick="openPlayerPanel('${p.player_id}')"` : '';
  return `<img class="lu-face" src="${p.face_url}" alt="" loading="lazy" width="36" height="36"${click}>`;
}

/* ── Player rows (Lineup and Roster tabs) ─────────────────────────────────────
   A row is the overall grade, then the name with a dim trail of stats and
   facts, then a line or two of ratings. Styles: .lu-* in main.css. */

function hitterGradesHtml(p, assignedPos) {
  // Two lines: hitting grades, then arm and fielding grades
  const hitPairs = [['CON',p.contact],['POW',p.power],['EYE',p.eye],['SPD',p.speed]];
  const defPairs = [
    ['ARM',p.arm],
    ['C',p.pos_c],['1B',p.pos_1b],['2B',p.pos_2b],['3B',p.pos_3b],
    ['SS',p.pos_ss],['LF',p.pos_lf],['CF',p.pos_cf],['RF',p.pos_rf],
  ];
  const hitHtml = hitPairs.filter(([,v])=>v)
    .map(([k,v])=>`<span><span class="gl">${k}</span><span class="${gradeClass(v)}">${v}</span></span>`)
    .join('');
  const aPos = (assignedPos||'').toUpperCase();
  const defHtml = defPairs.filter(([,v])=>v)
    .map(([k,v]) => {
      const isAssigned = k === aPos;
      return isAssigned
        ? `<span><span class="gl">${k}</span><span class="${gradeClass(v)}" style="color:var(--sky);font-weight:700;">${v}</span></span>`
        : `<span><span class="gl">${k}</span><span class="${gradeClass(v)}">${v}</span></span>`;
    }).join('');
  // The fielding line carries .lu-def so a list can hide it (Lineup tab's
  // Show Def toggle).
  return (hitHtml ? `<div class="lu-skills">${hitHtml}</div>` : '')
    + (defHtml ? `<div class="lu-skills lu-def">${defHtml}</div>` : '');
}

function pitcherGradesHtml(p) {
  return [['STF',p.stuff],['CTL',p.control],['STA',p.stamina],['REC',p.recovery],['GB',p.ground_balls]]
    .filter(([,v])=>v)
    .map(([k,v])=>`<span><span class="gl">${k}</span><span class="${gradeClass(v)}">${v}</span></span>`)
    .join('');
}

// "RUST" after the name of a player still rusty from an injury; the hover
// says which ratings are down and for how long.
function rustTag(p) {
  if (!p.rust) return '';
  const tip = `Rusty after his injury: ${p.rust.tip} Gone in about ${p.rust.days}d if he plays every day, about half that if he rests.`;
  return ` <span class="lu-rust" title="${tip}">RUST</span>`;
}

// A player's position as players see it, matching display_position() in
// src/player/positions.py: "P" for any pitcher, since a generated pitcher's
// SP or RP is only a leaning (it shows in his happiness instead); "2B" for
// the rest; '' for none.
function posLabel(pos) {
  const p = (pos || '').toLowerCase();
  if (!p) return '';
  return (p === 'sp' || p === 'rp' || p === 'p') ? 'P' : p.toUpperCase();
}

// The dim text that follows a player's name: "· .285 12HR · R/R · Age 27".
// Each piece stays whole, so a narrow screen wraps only at the dots.
// `stats` defaults to the hitting line; pass '' for none.
function nameTrailHtml(p, parts, stats = hitterStatsHtml(p)) {
  return '<span class="lu-trail">' + (stats ? [stats, ...parts] : parts)
    .map(t => ` <span class="lu-dot">·</span> <span class="lu-piece">${t}</span>`).join('') + '</span>';
}

function hitterStatsHtml(p) {
  return p.stat_avg != null
    ? `<span title="Batting average ${p.stat_avg}, ${p.stat_hr} home runs this season"><span style="color:var(--amber);">${p.stat_avg}</span> <span>${p.stat_hr}HR</span></span>`
    : '';
}

// A pitcher's stat line for the name trail: "12GS 74.1IP 3.45 ERA 8-4 3SV".
function pitcherTrailStatsHtml(p) {
  return p.stat_era != null
    ? `<span title="${p.stat_gs} games started, ${p.stat_ip} innings pitched, ${p.stat_era} ERA, ${p.stat_w} wins and ${p.stat_l} losses${p.stat_sv ? ', ' + p.stat_sv + ' saves' : ''} this season">`
      + `<span>${p.stat_gs}GS</span> <span>${p.stat_ip}IP</span> <span style="color:var(--amber);">${p.stat_era} ERA</span> <span>${p.stat_w}-${p.stat_l}${p.stat_sv ? ' ' + p.stat_sv + 'SV' : ''}</span></span>`
    : '';
}

// "#7" before a player's name: the number he wears for his team.
function jerseyTag(p) {
  return p.jersey_number != null ? `<span class="lu-jersey">#${p.jersey_number}</span>` : '';
}

// Happiness (src/player/happiness.py): "UNHAPPY", "WANTS TRADE" or "SITTING
// OUT" after the name. The hover says more; the player panel says why.
function moodTag(p) {
  const b = p.mood_badge;
  if (!b) return '';
  if (b.refusing) return '<span class="lu-mood lu-mood-bad" title="Unhappy enough to bench himself for a few days">SITTING OUT</span>';
  if (b.wants_trade) return '<span class="lu-mood lu-mood-bad" title="He has asked to be traded">WANTS TRADE</span>';
  return `<span class="lu-mood" title="He's ${b.mood}. Open his card to see why.">${b.mood.toUpperCase()}</span>`;
}

// "ICON" after a franchise icon's name (src/api/services/icons.py): years
// with the club and still good. Owners who care about icons hate losing one.
function iconTag(p) {
  const n = p.icon_seasons;
  if (!n) return '';
  return `<span class="lu-icon" title="Franchise icon: ${n} seasons with the club and still a top player. Owners who care about icons won't like seeing him traded or released.">ICON</span>`;
}

// "IL (12d)" after an injured player's name; the hover names the injury.
function ilTag(p) {
  if (!p.injured) return '';
  return ` <span style="font-size:10px;color:var(--red);"${p.injury_name ? ` title="${p.injury_name}"` : ''}>IL${p.injury_days ? ' (' + p.injury_days + 'd)' : ''}</span>`;
}
