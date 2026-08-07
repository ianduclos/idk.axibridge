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
      const item = e.target.closest(".menu-item");
      if (!item) return;
      // An item may NAME the control it drives (`data-target`) when that
      // control lives elsewhere — the Machine menu's Pen up is the Pen up
      // button in Settings › Jog & pen. This forwards the click to it, and
      // `menu_spec` reads the same attribute to build the native menu, so
      // both bars drive the identical element. It is a forward, not a second
      // implementation: nothing here knows what Pen up does.
      const target = item.dataset.target && document.querySelector(item.dataset.target);
      if (target) target.click();
      closeAll();
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
// This file still holds no opinion about the menu. WHAT has a state, HOW it
// is read and WHICH native item shows it all live in
// `axibridge/menu_spec.py`, which generates `window.__axbMenuProbe` and has
// the shell inject it — so the page runs an expression it was handed and
// names nothing itself. One definition, as with membership.
//
// It PASSES the result rather than letting the shell read it back: a pull
// would mean the shell calling evaluate_js from inside the js_api handler
// this call is awaiting, which is how a webview bridge deadlocks. A deadlock
// here looks exactly like the silent no-op this feature already shipped as
// once, so the shape that cannot deadlock wins.
//
// No-op in a browser tab: `window.pywebview` doesn't exist there, and the
// in-page bar shows its own ticks from CSS.
function watchForNativeMenu(bar) {
  const ping = () => {
    const probe = window.__axbMenuProbe;
    if (!probe) return;          // shell hasn't installed it yet; it re-pings
    window.pywebview?.api?.menu_changed?.(probe());
  };

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

  // and once at boot, so the menu opens correct before anything is touched.
  // The shell also reports once itself after installing the probe, because
  // this can fire before that install — belt and braces on an ordering we do
  // not control, and applying the same state twice costs nothing.
  if (window.pywebview) ping();
  else window.addEventListener("pywebviewready", ping, { once: true });
}
