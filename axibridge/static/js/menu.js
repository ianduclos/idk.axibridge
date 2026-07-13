// Header menu bar (File / View). Conservative by design: this module invents
// no new functionality — every item proxy-triggers a control that already
// exists elsewhere and is wired by its owning module (main.js). In
// particular the View items never touch PUT /api/project directly; they
// click the real #view-toggle buttons in the canvas toolbar (canvas.js/
// main.js own that request) so this file can't drift out of sync with it.

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
    if (m.dataset.menu === "view") updateViewChecks();
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
    // let the clicked item's own handler (saveProject, anchor download,
    // view-toggle proxy…) run first — this delegated listener just closes
    // the menu afterward, since it fires after the item's own bubbling.
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

  // View menu items proxy-click the existing #view-toggle buttons — the PUT
  // /api/project + canvas redraw logic stays exactly where it is (main.js).
  for (const item of bar.querySelectorAll("[data-view-proxy]")) {
    item.addEventListener("click", () => {
      document.querySelector(`#view-toggle button[data-view="${item.dataset.viewProxy}"]`)?.click();
    });
  }
}

function updateViewChecks() {
  const bar = $("menubar");
  for (const item of bar.querySelectorAll("[data-view-proxy]")) {
    const btn = document.querySelector(`#view-toggle button[data-view="${item.dataset.viewProxy}"]`);
    item.classList.toggle("checked", !!btn?.classList.contains("on"));
  }
}
