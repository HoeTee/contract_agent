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
