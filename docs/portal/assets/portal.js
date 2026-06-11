const state = {
  docs: [],
  activeId: null,
  filter: "all",
  query: "",
};

const els = {};

function icon(name) {
  return `<svg><use href="#${name}"></use></svg>`;
}

function groupBy(items, key) {
  return items.reduce((acc, item) => {
    const value = item[key] || "Other";
    acc[value] = acc[value] || [];
    acc[value].push(item);
    return acc;
  }, {});
}

function matches(doc) {
  const filterOk = state.filter === "all" || doc.category === state.filter;
  const haystack = [
    doc.title,
    doc.summary,
    doc.group,
    doc.category,
    ...(doc.tags || []),
    ...(doc.signals || []),
    ...(doc.paths || []),
  ].join(" ").toLowerCase();
  return filterOk && haystack.includes(state.query.toLowerCase());
}

function renderFlow(flow) {
  els.primaryFlow.innerHTML = flow
    .map((step) => `
      <div class="flow-step">
        ${icon(step.icon)}
        <strong>${step.title}</strong>
        <span>${step.text}</span>
      </div>
    `)
    .join("");
}

function renderTree(tree) {
  els.directoryTree.textContent = tree.replace(/\\n/g, "\n");
}

function renderNav() {
  const visible = state.docs.filter(matches);
  const groups = groupBy(visible, "group");
  els.docNav.innerHTML = Object.entries(groups)
    .map(([group, docs]) => `
      <section class="nav-section">
        <h2 class="nav-section-title">${group}</h2>
        ${docs
          .map((doc) => `
            <button class="nav-item ${doc.id === state.activeId ? "active" : ""}" data-doc-id="${doc.id}">
              ${doc.title}
              <span>${doc.summary}</span>
            </button>
          `)
          .join("")}
      </section>
    `)
    .join("");
}

function pathBlock(path) {
  return `
    <div class="code-path">
      <code>${path}</code>
      <button class="copy-button" type="button" data-copy="${path}" aria-label="复制路径">${icon("icon-copy")}</button>
    </div>
  `;
}

function renderCards() {
  const visible = state.docs.filter(matches);
  els.docCards.innerHTML = visible
    .map((doc) => `
      <article class="doc-card ${doc.id === state.activeId ? "expanded" : ""}" data-card-id="${doc.id}">
        <div class="doc-card-header">
          <div class="doc-title">
            <span class="doc-icon">${icon(doc.icon)}</span>
            <div>
              <h2>${doc.title}</h2>
              <p>${doc.summary}</p>
            </div>
          </div>
          <button class="detail-toggle" type="button" data-toggle="${doc.id}">
            详情 ${icon("icon-chevron")}
          </button>
        </div>
        <div class="tag-list">
          ${(doc.tags || []).map((tag) => `<span class="tag">${tag}</span>`).join("")}
        </div>
        <div class="signal-list">
          ${(doc.signals || []).map((signal) => `<div class="signal">${signal}</div>`).join("")}
        </div>
        <div class="detail-panel">
          ${(doc.details || []).map((detail) => `<p>${detail}</p>`).join("")}
          ${(doc.paths || []).slice(0, 3).map(pathBlock).join("")}
        </div>
      </article>
    `)
    .join("");
}

function renderInspector() {
  const doc = state.docs.find((item) => item.id === state.activeId) || state.docs[0];
  if (!doc) return;
  state.activeId = doc.id;
  els.inspectorTitle.textContent = doc.title;
  els.inspectorSummary.textContent = doc.summary;
  els.inspectorTags.innerHTML = (doc.tags || []).map((tag) => `<span class="tag">${tag}</span>`).join("");
  els.pathList.innerHTML = (doc.paths || [])
    .map((path) => `
      <div class="path-chip">
        ${path}
        <button class="copy-button" type="button" data-copy="${path}" aria-label="复制路径">${icon("icon-copy")}</button>
      </div>
    `)
    .join("");
  els.rawLink.classList.remove("disabled");
  els.rawLink.href = `../${encodeURIComponent(doc.md)}`;
}

function render() {
  renderNav();
  renderCards();
  renderInspector();
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
}

function bindEvents() {
  els.searchInput.addEventListener("input", (event) => {
    state.query = event.target.value.trim();
    render();
  });

  document.querySelectorAll(".filter-button").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".filter-button").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      state.filter = button.dataset.filter || "all";
      render();
    });
  });

  document.body.addEventListener("click", async (event) => {
    const copyButton = event.target.closest("[data-copy]");
    if (copyButton) {
      await copyText(copyButton.dataset.copy);
      copyButton.classList.add("copied");
      setTimeout(() => copyButton.classList.remove("copied"), 900);
      return;
    }

    const navButton = event.target.closest("[data-doc-id]");
    if (navButton) {
      state.activeId = navButton.dataset.docId;
      render();
      return;
    }

    const card = event.target.closest("[data-card-id]");
    const toggle = event.target.closest("[data-toggle]");
    if (toggle || card) {
      state.activeId = (toggle && toggle.dataset.toggle) || card.dataset.cardId;
      render();
      return;
    }
  });

  els.copyPathsButton.addEventListener("click", async () => {
    const doc = state.docs.find((item) => item.id === state.activeId);
    if (!doc) return;
    await copyText((doc.paths || []).join("\n"));
  });
}

function getPortalData() {
  if (window.DOCS_PORTAL_DATA) {
    return window.DOCS_PORTAL_DATA;
  }
  throw new Error("Docs portal data is missing. Expected assets/portal-data.js to load before portal.js.");
}

async function init() {
  Object.assign(els, {
    searchInput: document.querySelector("#searchInput"),
    docNav: document.querySelector("#docNav"),
    docCards: document.querySelector("#docCards"),
    primaryFlow: document.querySelector("#primaryFlow"),
    directoryTree: document.querySelector("#directoryTree"),
    inspectorTitle: document.querySelector("#inspectorTitle"),
    inspectorSummary: document.querySelector("#inspectorSummary"),
    inspectorTags: document.querySelector("#inspectorTags"),
    pathList: document.querySelector("#pathList"),
    rawLink: document.querySelector("#rawLink"),
    copyPathsButton: document.querySelector("#copyPathsButton"),
  });

  const manifest = getPortalData();
  state.docs = manifest.documents;
  state.activeId = state.docs[0]?.id || null;
  renderFlow(manifest.flow);
  renderTree(manifest.tree);
  bindEvents();
  render();
}

init();
