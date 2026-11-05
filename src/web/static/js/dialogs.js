// src/web/static/js/dialogs.js

// In-page dialogs, in place of the browser's own alert() and confirm().
// Loaded on every page from base.html; the look is .gm-modal in main.css.
//
// gmConfirm(opts) resolves true when the GM presses the action button.
// opts: {title, lines: [text], warn: a red warning line, ok: button label,
// tone: 'danger' | 'go', cancel: label, or null for an alert with one
// button}. Text is escaped.
//
// gmAlert(title, line) shows a message with a single OK button.
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
        ${opts.warn ? `<p class="gm-modal-line gm-modal-warn">${_esc(opts.warn)}</p>` : ''}
        <div class="gm-modal-btns">
          ${opts.cancel === null ? '' : `<button type="button" class="btn btn-secondary" data-ans="0">${_esc(opts.cancel || 'Cancel')}</button>`}
          <button type="button" class="btn btn-secondary gm-modal-ok ${opts.tone || ''}" data-ans="1">${_esc(opts.ok || 'OK')}</button>
        </div>
      </div>`;
    function done(ans) {
      document.removeEventListener('keydown', onKey, true);
      wrap.remove();
      if (back && back.focus && document.contains(back)) back.focus();
      resolve(ans);
    }
    function onKey(e) {
      if (e.key === 'Escape') { e.stopPropagation(); done(false); }
    }
    wrap.addEventListener('click', e => {
      const b = e.target.closest('[data-ans]');
      if (b) done(b.dataset.ans === '1');
      else if (e.target === wrap) done(false);
    });
    document.addEventListener('keydown', onKey, true);
    document.body.appendChild(wrap);
    wrap.querySelector('.gm-modal-ok').focus();
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
