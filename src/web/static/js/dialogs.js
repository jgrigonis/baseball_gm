// src/web/static/js/dialogs.js

// In-page dialogs, in place of the browser's own alert() and confirm().
// Loaded on every page from base.html; the look is .gm-modal in main.css.
//
// gmConfirm(opts) resolves true when the GM presses the action button.
// opts: {title, lines: [text], warn: a red warning line, ok: button label,
// tone: 'danger' | 'go', cancel: label, or null for an alert with one
// button, fields: [{name, label, value, min, max, step, hint}] number inputs;
// with fields it resolves {name: number} on OK, false otherwise}. Text is
// escaped.
//
// gmAlert(title, line) shows a message with a single OK button.
//
// gmToast(msg, kind) pops a short notice at the top of the screen (just
// under the top bar and tabs) that
// fades on its own: kind 'ok' (green, saves), 'err' (red, stays longer) or
// 'info' (plain). Use it instead of a status line beside a button. A server
// response can raise one with the HX-Trigger header
// {"gmToast": {"msg": "...", "kind": "ok"}}, and a page can raise one on
// load with data-toast="..." (+ data-toast-kind) on any element.
//
// A form (or its submit button) with data-confirm="Title?" asks first and
// only submits on yes. Optional data-confirm-text (a plain line),
// data-confirm-warn (a red line), data-confirm-ok (button label) and
// data-confirm-tone ('danger' | 'go') shape the dialog.
function _esc(t) {
  return String(t).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
window.gmConfirm = function(opts) {
  return new Promise(resolve => {
    const back = document.activeElement;
    const wrap = document.createElement('div');
    wrap.className = 'gm-modal-wrap';
    wrap.innerHTML = `
      <div class="gm-modal" role="dialog" aria-modal="true" aria-labelledby="gm-modal-title">
        <div class="gm-modal-title" id="gm-modal-title">${_esc(opts.title)}</div>
        ${(opts.lines || []).filter(Boolean).map(l => `<p class="gm-modal-line">${_esc(l)}</p>`).join('')}
        ${(opts.fields || []).map(f => `<label class="gm-modal-field"><span>${_esc(f.label)}</span>
          <input type="number" name="${_esc(f.name)}" value="${_esc(f.value ?? '')}"
                 ${f.min !== undefined ? `min="${_esc(f.min)}"` : ''} ${f.max !== undefined ? `max="${_esc(f.max)}"` : ''}
                 step="${_esc(f.step ?? 1)}" inputmode="decimal">
          ${f.hint ? `<small>${_esc(f.hint)}</small>` : ''}</label>`).join('')}
        ${opts.warn ? `<p class="gm-modal-line gm-modal-warn">${_esc(opts.warn)}</p>` : ''}
        <div class="gm-modal-btns">
          ${opts.cancel === null ? '' : `<button type="button" class="btn btn-secondary" data-ans="0">${_esc(opts.cancel || 'Cancel')}</button>`}
          <button type="button" class="btn btn-secondary gm-modal-ok ${opts.tone || ''}" data-ans="1">${_esc(opts.ok || 'OK')}</button>
        </div>
      </div>`;
    function done(ans) {
      document.removeEventListener('keydown', onKey, true);
      const values = {};
      wrap.querySelectorAll('.gm-modal-field input').forEach(i => { values[i.name] = parseFloat(i.value); });
      wrap.remove();
      if (back && back.focus && document.contains(back)) back.focus();
      resolve(opts.fields ? (ans ? values : false) : ans);
    }
    function onKey(e) {
      if (e.key === 'Escape') { e.stopPropagation(); done(false); }
      else if (e.key === 'Enter' && e.target.closest && e.target.closest('.gm-modal-field')) {
        e.preventDefault(); done(true);
      }
    }
    wrap.addEventListener('click', e => {
      const b = e.target.closest('[data-ans]');
      if (b) done(b.dataset.ans === '1');
      else if (e.target === wrap) done(false);
    });
    document.addEventListener('keydown', onKey, true);
    document.body.appendChild(wrap);
    (wrap.querySelector('.gm-modal-field input') || wrap.querySelector('.gm-modal-ok')).focus();
  });
};
window.gmAlert = function(title, line) {
  return gmConfirm({title, lines: line ? [line] : [], ok: 'OK', cancel: null});
};
// Forms that ask before they submit.
document.addEventListener('submit', e => {
  const form = e.target;
  const src = [e.submitter, form].find(el => el && el.dataset && el.dataset.confirm);
  if (!src) return;
  if (form._gmConfirmed) { form._gmConfirmed = false; return; }
  e.preventDefault();
  e.stopImmediatePropagation();
  const d = src.dataset;
  gmConfirm({
    title: d.confirm,
    lines: d.confirmText ? [d.confirmText] : [],
    warn: d.confirmWarn,
    ok: d.confirmOk,
    tone: d.confirmTone,
  }).then(ok => {
    if (!ok) return;
    form._gmConfirmed = true;
    if (form.requestSubmit) form.requestSubmit(e.submitter || undefined);
    else form.submit();
  });
}, true);

// Short notices at the top of the screen (see gmToast above).
window.gmToast = function(msg, kind) {
  if (!msg) return;
  kind = kind || 'info';
  let box = document.getElementById('gm-toasts');
  if (!box) {
    box = document.createElement('div');
    box.id = 'gm-toasts';
    box.setAttribute('aria-live', 'polite');
    document.body.appendChild(box);
  }
  // Just under whatever bar is pinned across the top: the top bar, and a
  // row of league tabs if there is one. The top bar wraps to two rows on
  // phones, so measure each time. Only bars across the top count: the league
  // pages' sidebar (also #tab-bar) runs the full height, and measuring it put
  // the toast below the bottom of the screen. Never lower than a third of
  // the way down, whatever is up there.
  let top = 0;
  document.querySelectorAll('.topbar, #tab-bar').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.height && r.width > r.height && r.top <= 1 + top && r.bottom > top) top = r.bottom;
  });
  top = Math.min(Math.max(0, top), window.innerHeight / 3);
  box.style.top = top + 10 + 'px';
  // The same notice twice in a row just restarts its timer.
  const last = box.lastElementChild;
  if (last && last.textContent === msg && !last.classList.contains('out')) last.remove();
  const el = document.createElement('div');
  el.className = 'gm-toast ' + kind;
  el.setAttribute('role', kind === 'err' ? 'alert' : 'status');
  el.textContent = msg;
  box.appendChild(el);
  while (box.children.length > 3) box.firstElementChild.remove();
  setTimeout(() => {
    el.classList.add('out');
    setTimeout(() => el.remove(), 260);
  }, kind === 'err' ? 5000 : 2500);
};
document.addEventListener('gmToast', e => {
  const d = e.detail || {};
  gmToast(d.msg || d.value, d.kind);
});
function _pageToasts(root) {
  (root || document).querySelectorAll('[data-toast]').forEach(el => {
    gmToast(el.dataset.toast, el.dataset.toastKind);
    el.removeAttribute('data-toast');
  });
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => _pageToasts());
else _pageToasts();
document.addEventListener('htmx:afterSwap', e => _pageToasts(e.target));
