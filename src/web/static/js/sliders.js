// Each slider shows its value as it moves. A slider with set choices keeps
// its hidden input (the value sent) and its position in step, either way:
// moving it sets the input, and a mode preset setting the input moves it.
function sliderParts(field) {
  return {
    range: field.querySelector('input[type=range]'),
    hidden: field.querySelector('input[type=hidden]'),
    out: field.querySelector('.slider-value'),
    choices: field.dataset.choices && JSON.parse(field.dataset.choices),
    shown: field.dataset.shown && JSON.parse(field.dataset.shown),
  };
}
function showSlider(field, fromRange) {
  const p = sliderParts(field);
  if (!p.choices) {
    p.out.textContent = p.range.value + (p.out.dataset.unit || '');
    return;
  }
  if (fromRange) {
    p.hidden.value = p.choices[p.range.value];
  } else {
    const i = p.choices.indexOf(Number(p.hidden.value));
    if (i >= 0) p.range.value = i;
  }
  const shown = p.shown[p.range.value];
  // ∞ is drawn bigger (.inf), like everywhere else it shows.
  if (shown === '∞') p.out.innerHTML = '<span class="inf">∞</span>';
  else p.out.textContent = shown;
}
function syncSliders() {
  document.querySelectorAll('.slider-field').forEach(function (f) { showSlider(f, false); });
}
document.querySelectorAll('.slider-field').forEach(function (f) {
  f.querySelector('input[type=range]').addEventListener('input', function () { showSlider(f, true); });
});
