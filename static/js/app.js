(() => {
  const path = window.location.pathname;
  document.querySelectorAll(".nav__item").forEach((a) => {
    const href = a.getAttribute("href") || "";
    try {
      const url = new URL(href, window.location.origin);
      if (url.pathname !== "/" && path.startsWith(url.pathname)) {
        a.style.background = "rgba(200,243,107,.18)";
        a.style.borderColor = "rgba(200,243,107,.28)";
        a.style.color = "rgba(255,255,255,.96)";
      }
    } catch {
      // ignore
    }
  });
})();

