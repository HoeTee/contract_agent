document.querySelectorAll("[data-loading-form]").forEach((form) => {
  if (document.querySelector(".status-box")) {
    const button = form.querySelector("button[type='submit']");
    if (button) button.disabled = true;
    return;
  }

  form.addEventListener("submit", () => {
    const button = form.querySelector("button[type='submit']");
    if (!button) return;
    button.textContent = button.dataset.loadingLabel || "Processing...";
    button.disabled = true;
  });
});

document.querySelectorAll("[data-confirm-delete]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    const username = form.dataset.confirmUsername || "this user";
    const first = window.confirm(`Delete user ${username}? This removes account login access.`);
    if (!first) {
      event.preventDefault();
      return;
    }

    const keepDataInput = form.querySelector("input[name='keep_data']");
    const keepsData = keepDataInput && keepDataInput.checked;
    const dataMessage = keepsData
      ? "User data directory will be kept, but the account will be deleted."
      : "User data directory will also be deleted.";
    const second = window.confirm(`${dataMessage}\nConfirm deleting user ${username}?`);
    if (!second) {
      event.preventDefault();
    }
  });
});

if (document.body.dataset.authCheck === "true") {
  const checkSession = async () => {
    try {
      const params = new URLSearchParams(window.location.search);
      const ctx = params.get("ctx");
      const statusUrl = ctx ? `/web/session/status?ctx=${encodeURIComponent(ctx)}` : "/web/session/status";
      const response = await fetch(statusUrl, {
        cache: "no-store",
        credentials: "same-origin",
      });
      if (response.status === 401) {
        window.location.replace("/web/login");
      }
    } catch (error) {
      // Keep the current page usable if the network check itself fails.
    }
  };

  window.setInterval(checkSession, 10000);
}
