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
  return [hitHtml, defHtml].filter(Boolean)
    .map(h => `<div class="lu-skills">${h}</div>`).join('');
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
  const tip = `Rusty: ${p.rust.text}. Gone in about ${p.rust.days}d if he plays every day, about half that if he rests.`;
  return ` <span class="lu-rust" title="${tip}">RUST</span>`;
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
    ? `<span style="color:var(--amber);">${p.stat_avg}</span> <span>${p.stat_hr}HR</span>`
    : '';
}

// A pitcher's stat line for the name trail: "12GS 74.1IP 3.45 ERA 8-4 3SV".
function pitcherTrailStatsHtml(p) {
  return p.stat_era != null
    ? `<span>${p.stat_gs}GS</span> <span>${p.stat_ip}IP</span> <span style="color:var(--amber);">${p.stat_era} ERA</span> <span>${p.stat_w}-${p.stat_l}${p.stat_sv ? ' ' + p.stat_sv + 'SV' : ''}</span>`
    : '';
}

// "IL (12d)" after an injured player's name; the hover names the injury.
function ilTag(p) {
  if (!p.injured) return '';
  return ` <span style="font-size:10px;color:var(--red);"${p.injury_name ? ` title="${p.injury_name}"` : ''}>IL${p.injury_days ? ' (' + p.injury_days + 'd)' : ''}</span>`;
}
