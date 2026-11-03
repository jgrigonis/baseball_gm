// src/web/static/js/table_sort.js

// Click-to-sort for any table with data-sortable. Headers with data-sort="text"
// or data-sort="num" become clickable; clicking the same header again reverses
// the order. A cell can carry data-sort-value to sort on something other than
// its visible text (e.g. a full timestamp behind a short date).
//
// A table that also has data-sort-url keeps its sort in the page URL
// (?sort=<column>&dir=asc|desc), so a refresh or a shared link shows the same
// order. Use it on at most one table per page.
document.addEventListener('DOMContentLoaded', function() {
  var slug = function(th) {
    return th.textContent.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  };

  document.querySelectorAll('table[data-sortable]').forEach(function(table) {
    var headers = table.querySelectorAll('th[data-sort]');
    var persist = table.hasAttribute('data-sort-url');

    var sortBy = function(th, asc) {
      var col = th.cellIndex;
      var num = th.dataset.sort === 'num';
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
    };

    headers.forEach(function(th) {
      th.addEventListener('click', function() {
        var asc = th.dataset.dir !== 'asc';
        sortBy(th, asc);
        if (persist) {
          var url = new URL(window.location.href);
          url.searchParams.set('sort', slug(th));
          url.searchParams.set('dir', asc ? 'asc' : 'desc');
          history.replaceState(history.state, '', url);
        }
      });
    });

    if (persist) {
      var params = new URLSearchParams(window.location.search);
      var want = params.get('sort');
      if (want) {
        var match = Array.from(headers).find(function(th) { return slug(th) === want; });
        if (match) sortBy(match, params.get('dir') !== 'desc');
      }
    }
  });
});
