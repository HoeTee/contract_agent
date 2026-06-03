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

document.querySelectorAll("[data-confirm-delete]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    const username = form.dataset.confirmUsername || "该用户";
    const first = window.confirm(`确认删除用户 ${username}？此操作会移除账号登录权限。`);
    if (!first) {
      event.preventDefault();
      return;
    }

    const keepDataInput = form.querySelector("input[name='keep_data']");
    const keepsData = keepDataInput && keepDataInput.checked;
    const dataMessage = keepsData
      ? "当前选择会保留用户数据目录，但账号会被删除。"
      : "当前未选择保留用户数据，用户目录也会被删除。";
    const second = window.confirm(`${dataMessage}\n再次确认删除用户 ${username}？`);
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
      const statusUrl = ctx ? `/session/status?ctx=${encodeURIComponent(ctx)}` : "/session/status";
      const response = await fetch(statusUrl, {
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
