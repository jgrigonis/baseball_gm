// src/web/static/js/table_sort.js

// Click-to-sort for any table with data-sortable. Headers with data-sort="text"
// or data-sort="num" become clickable; clicking the same header again reverses
// the order. A cell can carry data-sort-value to sort on something other than
// its visible text (e.g. a full timestamp behind a short date).
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('table[data-sortable]').forEach(function(table) {
    var headers = table.querySelectorAll('th[data-sort]');
    headers.forEach(function(th) {
      th.addEventListener('click', function() {
        var col = th.cellIndex;
        var num = th.dataset.sort === 'num';
        var asc = th.dataset.dir !== 'asc';
        headers.forEach(function(h) { delete h.dataset.dir; });
        th.dataset.dir = asc ? 'asc' : 'desc';
        var body = table.tBodies[0];
        var rows = Array.from(body.rows);
        var key = function(row) {
          var cell = row.cells[col];
          var v = cell.dataset.sortValue != null ? cell.dataset.sortValue : cell.textContent.trim();
          return num ? (parseFloat(v) || 0) : v.toLowerCase();
        };
        rows.sort(function(a, b) {
          var x = key(a), y = key(b);
          var c = num ? x - y : x.localeCompare(y);
          return asc ? c : -c;
        });
        rows.forEach(function(r) { body.appendChild(r); });
      });
    });
  });
});
