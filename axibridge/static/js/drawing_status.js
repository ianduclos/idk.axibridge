// One shared activity indicator, independent of generator/plot progress.
// A token per operation keeps overlapping edits and nested refreshes honest.
const pending = new Set();
let started = 0;
let timer = null;

function render() {
  const status = document.getElementById("drawing-status");
  if (!status) return;
  const elapsed = performance.now() - started;
  status.hidden = !pending.size || elapsed < 150;
  document.getElementById("drawing-elapsed").textContent =
    elapsed >= 1000 ? ` · ${(elapsed / 1000).toFixed(1)}s` : "";
}

export function beginDrawingUpdate() {
  const token = {};
  pending.add(token);
  if (pending.size === 1) {
    started = performance.now();
    timer = setInterval(render, 100);
  }
  render();
  return () => {
    pending.delete(token);
    if (!pending.size) {
      clearInterval(timer);
      timer = null;
    }
    render();
  };
}

export function restartDrawingUpdate() {
  started = performance.now();
  render();
}
