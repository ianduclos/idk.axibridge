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
}
