// scripts/measure_cap_logos.js
//
// Measures the logo on every team's cap.svg and writes the boxes to
// src/player/cap_logo_boxes.json. Player faces (src/player/face.py) use the
// box to center and size the team's logo on the front of the cap.
//
// Run it after adding a team or changing a cap logo:
//   node scripts/measure_cap_logos.js
// It needs Playwright with Chromium (preinstalled in cloud sessions).
//
// The logo is what face.cap_parts() takes as the logo: the cap's <defs> plus
// every element after the brim, minus brim trim (paths starting "M40 120").

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const UNIFORMS = path.join(ROOT, 'src/web/static/img/uniforms');
const OUT = path.join(ROOT, 'src/player/cap_logo_boxes.json');

function logoMarkup(svg) {
  const defs = (svg.match(/<defs>[\s\S]*?<\/defs>/) || [''])[0];
  const lines = svg.split('\n');
  const brim = lines.findIndex(l => l.includes('d="M36 120'));
  const logo = lines.slice(brim + 1)
    .filter(l => !l.includes('</svg>') && !l.includes('d="M40 120'))
    .join('\n');
  return defs + logo;
}

(async () => {
  const slugs = fs.readdirSync(UNIFORMS)
    .filter(d => fs.existsSync(path.join(UNIFORMS, d, 'cap.svg')))
    .sort();
  const html = slugs.map(s => {
    const svg = fs.readFileSync(path.join(UNIFORMS, s, 'cap.svg'), 'utf8');
    return `<svg data-slug="${s}" width="240" height="170" viewBox="0 0 240 170"><g class="logo">${logoMarkup(svg)}</g></svg>`;
  }).join('');
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setContent(html);
  const boxes = await page.$$eval('svg[data-slug]', els => Object.fromEntries(els.map(el => {
    const b = el.querySelector('.logo').getBBox();
    const r = v => Math.round(v * 10) / 10;
    return [el.dataset.slug, [r(b.x), r(b.y), r(b.width), r(b.height)]];
  })));
  await browser.close();
  const rows = Object.entries(boxes).map(([k, v]) => `  ${JSON.stringify(k)}: ${JSON.stringify(v)}`);
  fs.writeFileSync(OUT, '{\n' + rows.join(',\n') + '\n}\n');
  console.log(`Wrote ${Object.keys(boxes).length} logo boxes to ${path.relative(ROOT, OUT)}`);
})();
