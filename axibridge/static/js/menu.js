// Header menu bar (File / Edit / View). Conservative by design: this module
// invents no new functionality. It owns opening, closing and keyboard
// dismissal — nothing else. Every ITEM is a real control wired by its owning
// module (main.js): #btn-save, #btn-undo, #btn-redo, and the two #view-toggle
// buttons, which moved here bodily from the canvas toolbar rather than being
// re-implemented as menu proxies. That is the rule this file exists to keep:
// a menu item must never be a second implementation of something the app can
// already do, or the two drift and the menu starts lying.

const $ = (id) => document.getElementById(id);

export function initMenu() {
  const bar = $("menubar");
  if (!bar || bar.dataset.menuInit) return; // idempotent — safe to call on every initTabs()
  bar.dataset.menuInit = "1";

  const menus = Array.from(bar.querySelectorAll(".menu"));

  function closeAll() {
    for (const m of menus) {
      m.classList.remove("open");
      m.querySelector(".menu-trigger")?.setAttribute("aria-expanded", "false");
    }
  }
  function isOpen(m) { return m.classList.contains("open"); }
  function anyOpen() { return menus.some(isOpen); }
  function openMenu(m) {
    closeAll();
    m.classList.add("open");
    m.querySelector(".menu-trigger")?.setAttribute("aria-expanded", "true");
  }

  for (const m of menus) {
    const trigger = m.querySelector(".menu-trigger");
    trigger.addEventListener("click", (e) => {
      e.stopPropagation();
      isOpen(m) ? closeAll() : openMenu(m);
    });
    // hovering across an already-open menubar switches menus
    trigger.addEventListener("mouseenter", () => {
      if (anyOpen() && !isOpen(m)) openMenu(m);
    });
    // let the clicked item's own handler (saveProject, undo, the view
    // buttons, the download anchor) run first — this delegated listener just
    // closes the menu afterward, since it fires after the item's own bubbling.
    m.querySelector(".menu-panel").addEventListener("click", (e) => {
      if (e.target.closest(".menu-item")) closeAll();
    });
  }

  document.addEventListener("click", (e) => {
    if (!bar.contains(e.target)) closeAll();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeAll();
  });

  watchForNativeMenu(bar);
}

// In the app shell the system menu bar is the visible one and this bar is
// display:none, so the checkmarks a user actually sees are native. They can
// only be right if something says when a control changed.
//
// This is the whole of the page's involvement, on purpose: it sends no data
// and names no control. WHAT has a state, HOW that state is read and WHICH
// native item shows it all live in `axibridge/menu_spec.py`, which also
// generates the read-back expression — so this file cannot hold a second,
// drifting opinion about the menu. That split is the fix for the bug that
// started all this (two hand-maintained menus), applied to state as well as
// to membership.
//
// No-op in a browser tab: `window.pywebview` doesn't exist there, and the
// in-page bar shows its own ticks from CSS.
function watchForNativeMenu(bar) {
  const ping = () => window.pywebview?.api?.menu_changed?.();

  let queued = false;
  const schedule = () => {
    if (queued) return;         // several class flips per click is normal
    queued = true;
    queueMicrotask(() => { queued = false; ping(); });
  };

  // `.on` is toggled by main.js on radio-ish items; `change` covers the real
  // checkboxes. Observing rather than asking main.js to call us keeps the
  // controls' owners unaware of the menu, which is what let them move here
  // bodily in the first place.
  new MutationObserver(schedule).observe(bar, {
    subtree: true, attributes: true, attributeFilter: ["class", "checked"],
  });
  bar.addEventListener("change", schedule);

  // and once at boot, so the menu opens correct before anything is touched
  if (window.pywebview) ping();
  else window.addEventListener("pywebviewready", ping, { once: true });
}
