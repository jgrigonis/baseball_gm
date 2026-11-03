// scripts/mobile_check.js
//
// Loads every page of a league at phone width (375px) and reports any page
// that's wider than the screen, with the elements that stick out. Use it after
// changing a page's layout so phones don't regress.
//
//   node scripts/mobile_check.js --user NAME --password PW --league LEAGUE_ID
//   node scripts/mobile_check.js ... --base http://127.0.0.1:8000 --width 360
//   node scripts/mobile_check.js ... --shots /tmp/shots   # also save screenshots
//
// It signs in as NAME, so use a GM of the league. A league in season shows the
// most tabs. Exits 1 if any page is too wide. It needs Playwright with
// Chromium (preinstalled in cloud sessions).
//
// Tables inside an overflow-x: auto box (.table-scroll) are fine: only the
// table slides. What counts is the tab or page itself sliding sideways.

const { chromium } = require('playwright');

function arg(name, fallback) {
  const i = process.argv.indexOf('--' + name);
  return i > -1 ? process.argv[i + 1] : fallback;
}

const BASE = arg('base', 'http://127.0.0.1:8000');
const USER = arg('user');
const PASSWORD = arg('password');
const LEAGUE = arg('league');
const WIDTH = +arg('width', 375);
const SHOTS = arg('shots');

const LEAGUE_PAGES = [
  '', 'roster', 'lineup', 'trades', 'schedule', 'standings', 'leaders', 'stats',
  'strategy', 'headlines', 'allstar', 'playoffs', 'draft', 'draft/results',
  'league', 'history', 'welcome',
];
const SITE_PAGES = ['/leagues/', '/leagues/new', '/account', `/gms/${USER}`];

// Runs in the page: the scrolling pane's width, and the outermost elements
// that reach past the right edge without a sideways-scrolling box around them.
function measure() {
  const vw = document.documentElement.clientWidth;
  const pane = document.getElementById('tab-content') || document.querySelector('.page-content');
  const isPane = el => el === pane || el.id === 'main-content';
  const out = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.right <= vw + 1) continue;
    const cs = getComputedStyle(el);
    if (cs.position === 'fixed' || cs.visibility === 'hidden') continue;
    if (el.closest('#tab-bar, .nav-menu-panel, .player-panel')) continue;
    let a = el.parentElement, boxed = false;
    for (; a && !isPane(a); a = a.parentElement) {
      const ox = getComputedStyle(a).overflowX;
      if ((ox === 'auto' || ox === 'scroll') && a.getBoundingClientRect().right <= vw + 1) { boxed = true; break; }
    }
    if (boxed || out.some(o => o.el.contains(el))) continue;
    const cls = typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).join('.') : '';
    out.push({ el, label: `${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}${cls} → ${Math.round(r.right)}px` });
  }
  return {
    width: Math.max(document.documentElement.scrollWidth, pane ? pane.scrollWidth : 0),
    vw,
    wide: out.slice(0, 6).map(o => o.label),
  };
}

(async () => {
  if (!USER || !PASSWORD || !LEAGUE) {
    console.error('Usage: node scripts/mobile_check.js --user NAME --password PW --league LEAGUE_ID');
    process.exit(2);
  }
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: WIDTH, height: 812 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true,
  });
  const page = await ctx.newPage();
  const login = await ctx.request.post(BASE + '/auth/login', { form: { username: USER, password: PASSWORD } });
  if (!login.ok()) { console.error('Sign in failed:', login.status()); process.exit(2); }

  const urls = [...LEAGUE_PAGES.map(p => `/leagues/${LEAGUE}/${p}`), ...SITE_PAGES];
  let bad = 0;
  for (const url of urls) {
    const res = await page.goto(BASE + url);
    if (!res || res.status() >= 400) { console.log(`skip  ${url} (${res ? res.status() : 'no response'})`); continue; }
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);
    const m = await page.evaluate(measure);
    const ok = m.width <= m.vw + 1 && m.wide.length === 0;
    if (!ok) bad++;
    console.log(`${ok ? 'ok   ' : 'WIDE '} ${url}${ok ? '' : `  (${m.width}px)`}`);
    for (const w of m.wide) console.log(`        ${w}`);
    if (SHOTS) {
      const name = url.replace(/^\/|\/$/g, '').replace(/[^a-z0-9]+/gi, '-').replace(LEAGUE, 'L') || 'home';
      await page.screenshot({ path: `${SHOTS}/${name}.png` });
    }
  }
  await browser.close();
  console.log(bad ? `\n${bad} page(s) wider than ${WIDTH}px.` : `\nEvery page fits in ${WIDTH}px.`);
  process.exit(bad ? 1 : 0);
})();
