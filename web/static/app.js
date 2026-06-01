document.querySelectorAll("[data-loading-form]").forEach((form) => {
  if (document.querySelector(".status-box")) {
    const button = form.querySelector("button[type='submit']");
    if (button) button.disabled = true;
    window.setTimeout(() => window.location.reload(), 5000);
    return;
  }

  form.addEventListener("submit", () => {
    const button = form.querySelector("button[type='submit']");
    if (!button) return;
    button.textContent = button.dataset.loadingLabel || "处理中...";
    button.disabled = true;
  });
});

if (document.body.dataset.authCheck === "true") {
  const checkSession = async () => {
    try {
      const response = await fetch("/session/status", {
        cache: "no-store",
        credentials: "same-origin",
      });
      if (response.status === 401) {
        window.location.replace("/login");
      }
    } catch (error) {
      // Keep the current page usable if the network check itself fails.
    }
  };

  window.setInterval(checkSession, 10000);
}
