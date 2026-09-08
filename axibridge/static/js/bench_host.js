// Shared popup lifecycle. No generator, event, history or project mutation logic.
const $ = id => document.getElementById(id);
let session = null;
let opener = null;
let inertBefore = [];
let returnTo = null;
let wired = false;
let epoch = 0;
export const benchProjectEpoch = () => epoch;

export function initBenchHost() {
  if (wired || !$('process-popup')) return;
  wired = true;
  const popup = $('process-popup');
  popup.setAttribute('role', 'dialog');
  popup.setAttribute('aria-modal', 'true');
  popup.setAttribute('aria-labelledby', 'process-title');
  popup.tabIndex = -1;
  $('process-expand').onclick = () => {
    const expanded = popup.classList.toggle('expanded');
    $('process-expand').textContent = expanded ? 'Restore' : 'Expand';
    $('process-expand').setAttribute('aria-pressed', String(expanded));
  };
  $('process-controls-toggle').onclick = () => {
    const visible = popup.classList.toggle('controls-open');
    $('process-controls-toggle').textContent = visible ? 'Hide controls' : 'Controls';
    $('process-controls-toggle').setAttribute('aria-expanded', String(visible));
  };
  $('process-close').onclick = () => session?.close();
  $('bench-return').onclick = () => returnTo?.();
  $('process-stop').onclick = () => $('btn-stop')?.click();
  const stop = $('btn-stop');
  const syncStop = () => { $('process-stop').disabled = !stop || stop.disabled || Boolean(stop.closest('[hidden]')); };
  syncStop();
  if (stop) new MutationObserver(syncStop).observe(stop.closest('#machine-state') || stop, { attributes:true, subtree:true, attributeFilter:['disabled','hidden'] });
  popup.addEventListener('mousedown', e => {
    if (e.target === popup) session?.close();
  });
  document.addEventListener('keydown', e => {
    if (!session || popup.hidden) return;
    if (e.key === 'Escape') {
      e.preventDefault(); e.stopImmediatePropagation();
      if (!session.cancelGesture?.()) session.close();
    } else if (e.key === 'Tab') {
      const controls = [...popup.querySelectorAll('button,input,select,textarea,summary,a[href],[tabindex="0"]')]
        .filter(el => !el.disabled && el.getClientRects().length && !el.closest('[hidden]'));
      const first = controls[0], last = controls.at(-1);
      if (!first) { e.preventDefault(); popup.focus(); return; }
      if (e.shiftKey && (document.activeElement === first || !popup.contains(document.activeElement))) {
        e.preventDefault(); last.focus();
      } else if (!e.shiftKey && (document.activeElement === last || !popup.contains(document.activeElement))) {
        e.preventDefault(); first.focus();
      }
    } else if (!e.target.matches('input,textarea,select,[contenteditable="true"]')) {
      // Let the adapter's capture-phase local undo run first; do not let the
      // hidden composition consume Delete or document shortcuts.
      if (e.key === 'Delete' || e.key === 'Backspace' || e.metaKey || e.ctrlKey) {
        e.preventDefault(); e.stopImmediatePropagation();
      }
    }
  }, true);
}

export function openBenchShell({ close, cancelGesture, reopen, origin = '' }) {
  initBenchHost();
  const popup = $('process-popup');
  if (!session) {
    opener = document.activeElement;
    inertBefore = [...document.body.children]
      .filter(el => el !== popup && el.tagName !== 'SCRIPT')
      .map(el => [el, el.inert]);
    inertBefore.forEach(([el]) => { el.inert = true; });
    // Opening is always the default popup. Expand/Restore never opens a new draft.
    popup.classList.remove('expanded', 'controls-open');
    $('process-expand').textContent = 'Expand';
    $('process-expand').setAttribute('aria-pressed', 'false');
    $('process-controls-toggle').textContent = 'Controls';
    $('process-controls-toggle').setAttribute('aria-expanded', 'false');
  }
  session = { close, cancelGesture };
  returnTo = reopen || null;
  $('bench-return').hidden = !returnTo;
  $('process-origin').textContent = origin;
  clearBenchError();
  popup.hidden = false;
  $('process-close').focus({ preventScroll: true });
}
export function closeBenchShell() {
  $('process-popup').hidden = true;
  session = null;
  inertBefore.forEach(([el, value]) => { el.inert = value; });
  inertBefore = [];
  clearBenchError();
  if (opener?.isConnected && opener.getClientRects().length) opener.focus({ preventScroll: true });
  else $('bench-return')?.focus({ preventScroll: true });
}
export function clearBenchError() {
  if (!$('process-error')) return;
  $('process-error').hidden = true;
  $('process-error-message').textContent = '';
  $('process-retry').onclick = null;
}
export function showBenchError(error, retry = null) {
  $('process-error-message').textContent = error?.message || String(error);
  $('process-error').hidden = false;
  $('process-retry').hidden = !retry;
  $('process-retry').onclick = retry;
}
export function resetBenchProject() {
  session?.close();
  epoch++;
  returnTo = null;
  if ($('bench-return')) $('bench-return').hidden = true;
  document.dispatchEvent(new Event('bench-project-reset'));
}
