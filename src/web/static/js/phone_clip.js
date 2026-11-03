// src/web/static/js/phone_clip.js

// Long lists on phones. A table with data-phone-clip shows only its first 8
// rows under 700px, with a "Show all N" button under it, so the block below
// the list comes into view after a short scroll. Wider screens show every
// row: the hiding is CSS inside the phone breakpoint (main.css), so this
// script only adds the class and the button.
(function () {
  var KEEP = 8;  // rows shown; must match the nth-child in main.css

  function clip(root) {
    (root || document).querySelectorAll('table[data-phone-clip]:not([data-clip-ready])').forEach(function (t) {
      t.setAttribute('data-clip-ready', '');
      var body = t.tBodies[0];
      var n = body ? body.rows.length : 0;
      if (n <= KEEP + 2) return;  // hiding one or two rows isn't worth a button
      t.classList.add('clipped');
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn btn-secondary clip-more';
      var more = 'Show all ' + n + ' ▾';
      btn.textContent = more;
      btn.addEventListener('click', function () {
        var clipped = t.classList.toggle('clipped');
        btn.textContent = clipped ? more : 'Show fewer ▴';
        if (clipped) btn.scrollIntoView({ block: 'nearest' });
      });
      // After the table's sideways-scroll box, so the button stays full width.
      var box = t.closest('.table-scroll') || t;
      box.parentNode.insertBefore(btn, box.nextSibling);
    });
  }

  document.addEventListener('DOMContentLoaded', function () { clip(); });
  // Tabs swap in without a page load.
  document.addEventListener('htmx:afterSettle', function (e) { clip(e.target); });
})();
