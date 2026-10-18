/* Progressive enhancement: the ordinary portal links also work without JS. */
(() => {
  "use strict";
  const initializeNavigation = () => {
  const nav = document.getElementById("ap-site-nav");
  if (!nav || nav.dataset.apInitialized === "true") return;
  nav.dataset.apInitialized = "true";
  document.body.classList.add("ap-has-nav");

  const back = nav.querySelector("[data-ap-back]");
  let safeBack = false;
  if (back) {
    try {
      const portal = new URL(back.href, window.location.href);
      const project = new URL("../", portal);
      const previous = document.referrer ? new URL(document.referrer) : null;
      safeBack = Boolean(previous && previous.origin === portal.origin &&
        previous.pathname.startsWith(project.pathname) && window.history.length > 1);
    } catch (_) {
      safeBack = false;
    }
    back.setAttribute("aria-label", safeBack ? "Volver a la página anterior" : "Volver al portal");
    back.title = safeBack ? "Regresar a la página anterior de este sitio" : "Regresar al portal de resultados";
    back.addEventListener("click", (event) => {
      if (safeBack && event.button === 0 && !event.ctrlKey && !event.metaKey &&
          !event.shiftKey && !event.altKey) {
        event.preventDefault();
        window.history.back();
      }
    });
  }

  for (const link of nav.querySelectorAll("a[href]")) {
    if (link === back || link.getAttribute("href").startsWith("#")) continue;
    const target = new URL(link.href, window.location.href);
    if (target.origin === window.location.origin && target.pathname === window.location.pathname && !target.hash) {
      link.setAttribute("aria-current", "page");
    }
  }

  const list = nav.querySelector("[data-ap-sections]");
  const details = list && list.closest("details");
  if (list && details) {
    const headings = [...document.querySelectorAll("h2, h3")].filter((heading) =>
      heading.id !== "toc-title" && !heading.closest("nav, #TOC, .quarto-margin-sidebar"));
    // Keep an exceptionally large document's menu useful without listing every file.
    const selected = headings.length > 120 ? headings.filter((h) => h.tagName === "H2") : headings;
    const fragment = document.createDocumentFragment();
    let count = 0;
    for (const heading of selected) {
      let id = heading.getAttribute("data-anchor-id") || heading.id ||
        (heading.closest("section[id]") || {}).id;
      if (!id || !document.getElementById(id)) {
        let sequence = count + 1;
        while (document.getElementById(`ap-section-${sequence}`)) sequence += 1;
        id = `ap-section-${sequence}`;
        heading.id = id;
      }
      const copy = heading.cloneNode(true);
      for (const accessory of copy.querySelectorAll("a.anchorjs-link, a.anchor-link, .header-anchor, .visually-hidden")) {
        accessory.remove();
      }
      const label = copy.textContent.replace(/\s+/g, " ").trim();
      if (!label) continue;
      const item = document.createElement("li");
      if (heading.tagName === "H3") item.className = "ap-subsection";
      const link = document.createElement("a");
      link.href = `#${encodeURIComponent(id)}`;
      link.textContent = label;
      item.appendChild(link);
      fragment.appendChild(item);
      count += 1;
    }
    list.replaceChildren(fragment);
    details.hidden = count === 0;
    list.addEventListener("click", (event) => {
      if (event.target.closest("a")) details.open = false;
    });
    nav.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && details.open) {
        details.open = false;
        details.querySelector("summary").focus();
      }
    });
    document.addEventListener("click", (event) => {
      if (details.open && !details.contains(event.target)) details.open = false;
    });
  }

  const measure = () => {
    document.documentElement.style.setProperty("--ap-nav-height", `${Math.ceil(nav.getBoundingClientRect().height)}px`);
  };
  measure();
  window.addEventListener("resize", measure, {passive: true});
  if (typeof ResizeObserver !== "undefined") new ResizeObserver(measure).observe(nav);
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeNavigation, {once: true});
  } else {
    initializeNavigation();
  }
})();
