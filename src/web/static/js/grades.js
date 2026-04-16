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