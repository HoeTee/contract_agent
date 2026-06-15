const state = {
  docs: [],
  content: {},
  diagram: null,
  view: "home", // "home" | "doc"
  activeId: null,
  filter: "all",
  query: "",
};

const els = {};

function icon(name) {
  return `<svg><use href="#${name}"></use></svg>`;
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// Escape HTML, turn `inline code` into <code>, and linkify bare URLs.
function inline(text) {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noreferrer">$1</a>');
}

function groupBy(items, key) {
  return items.reduce((acc, item) => {
    const value = item[key] || "其他";
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
  ]
    .join(" ")
    .toLowerCase();
  return filterOk && haystack.includes(state.query.toLowerCase());
}

/* ---------------- architecture diagram ---------------- */
function anchorPoints(from, to) {
  const fc = { x: from.x + from.w / 2, y: from.y + from.h / 2 };
  const tc = { x: to.x + to.w / 2, y: to.y + to.h / 2 };
  const dx = tc.x - fc.x;
  const dy = tc.y - fc.y;
  let start;
  let end;
  if (Math.abs(dx) >= Math.abs(dy)) {
    start = dx > 0 ? { x: from.x + from.w, y: fc.y } : { x: from.x, y: fc.y };
    end = dx > 0 ? { x: to.x, y: tc.y } : { x: to.x + to.w, y: tc.y };
  } else {
    start = dy > 0 ? { x: fc.x, y: from.y + from.h } : { x: fc.x, y: from.y };
    end = dy > 0 ? { x: tc.x, y: to.y } : { x: tc.x, y: to.y + to.h };
  }
  return { start, end };
}

function buildDiagramSVG(diagram) {
  const nodeById = Object.fromEntries(diagram.nodes.map((n) => [n.id, n]));

  const markers = ["main", "flow", "loop", "support"]
    .map(
      (kind) => `
      <marker id="arrow-${kind}" class="arrow-${kind}" viewBox="0 0 10 10" refX="8" refY="5"
        markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0 0L10 5L0 10z" />
      </marker>
    `
    )
    .join("");

  const edges = diagram.edges
    .map((edge) => {
      const from = nodeById[edge.from];
      const to = nodeById[edge.to];
      if (!from || !to) return "";
      const { start, end } = anchorPoints(from, to);
      const mid = { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 };
      const path = `M${start.x} ${start.y}L${end.x} ${end.y}`;
      const startMarker = edge.bidir ? `marker-start="url(#arrow-${edge.kind})"` : "";
      const label = edge.label
        ? `<g class="edge-label" transform="translate(${mid.x} ${mid.y})">
             <rect x="${-edge.label.length * 6.5 - 6}" y="-11" width="${edge.label.length * 13 + 12}" height="22" rx="6" />
             <text x="0" y="4" text-anchor="middle">${edge.label}</text>
           </g>`
        : "";
      return `
        <path class="arch-edge edge-${edge.kind}" d="${path}"
          marker-end="url(#arrow-${edge.kind})" ${startMarker} />
        ${label}`;
    })
    .join("");

  const nodes = diagram.nodes
    .map((node) => {
      const inner =
        `<span class="arch-node-icon">${icon(node.icon)}</span>` +
        `<span class="arch-node-text"><strong>${node.title}</strong><small>${node.sub}</small></span>`;
      const cls = `arch-node node-${node.kind}`;
      const el = node.docId
        ? `<button xmlns="http://www.w3.org/1999/xhtml" type="button" class="${cls}" data-doc-id="${node.docId}">${inner}</button>`
        : `<div xmlns="http://www.w3.org/1999/xhtml" class="${cls} static">${inner}</div>`;
      return `<foreignObject x="${node.x}" y="${node.y}" width="${node.w}" height="${node.h}">${el}</foreignObject>`;
    })
    .join("");

  const parts = diagram.viewBox.split(/\s+/).map(Number);
  const vbw = parts[2];
  const vbh = parts[3];
  return `
    <svg class="arch-svg" style="aspect-ratio: ${vbw} / ${vbh}" viewBox="${diagram.viewBox}" role="img" aria-label="架构图">
      <defs>${markers}</defs>
      <g class="arch-edges">${edges}</g>
      <g class="arch-nodes">${nodes}</g>
    </svg>`;
}

function renderDiagram(diagram) {
  if (!els.archDiagram || !diagram) return;
  els.archDiagram.innerHTML = buildDiagramSVG(diagram);
}

function renderFlow(flow) {
  els.primaryFlow.innerHTML = flow
    .map(
      (step) => `
      <div class="flow-step">
        ${icon(step.icon)}
        <strong>${step.title}</strong>
        <span>${step.text}</span>
      </div>
    `
    )
    .join("");
}

function renderTree(tree) {
  els.directoryTree.textContent = tree.replace(/\\n/g, "\n");
}

/* ---------------- sidebar list ---------------- */
function renderNav() {
  const visible = state.docs.filter(matches);
  if (!visible.length) {
    els.docNav.innerHTML = `<p class="nav-empty">没有匹配的文档。</p>`;
  } else {
    const groups = groupBy(visible, "group");
    els.docNav.innerHTML = Object.entries(groups)
      .map(
        ([group, docs]) => `
        <section class="nav-section">
          <h2 class="nav-section-title">${group}</h2>
          ${docs
            .map(
              (doc) => `
              <button class="nav-item ${doc.id === state.activeId && state.view === "doc" ? "active" : ""}" data-doc-id="${doc.id}">
                <strong>${doc.title}</strong>
                <span>${doc.summary}</span>
              </button>
            `
            )
            .join("")}
        </section>
      `
      )
      .join("");
  }
  els.homeButton.classList.toggle("active", state.view === "home");
}

/* ---------------- content block renderer ---------------- */
function renderBlock(block) {
  switch (block.type) {
    case "heading":
      return `<h2 class="content-h">${inline(block.text)}</h2>`;
    case "para":
      return `<p class="content-p">${inline(block.text)}</p>`;
    case "code":
      return `<pre class="content-code"><code>${escapeHtml(block.text)}</code></pre>`;
    case "callout":
      return `<div class="content-callout">${
        block.title ? `<span class="callout-title">${inline(block.title)}</span>` : ""
      }<span>${inline(block.text)}</span></div>`;
    case "list": {
      const tag = block.ordered ? "ol" : "ul";
      const items = (block.items || []).map((it) => `<li>${inline(it)}</li>`).join("");
      return `<${tag} class="content-list">${items}</${tag}>`;
    }
    case "table": {
      const head = (block.headers || []).map((h) => `<th>${inline(h)}</th>`).join("");
      const rows = (block.rows || [])
        .map((row) => `<tr>${row.map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`)
        .join("");
      return `<div class="content-table-wrap"><table class="content-table">
        <thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>`;
    }
    case "diagram": {
      const legend = (block.legend || [])
        .map((l) => `<span class="legend-item ${l.cls}">${inline(l.label)}</span>`)
        .join("");
      return `<figure class="content-diagram">
        <div class="arch-canvas">${buildDiagramSVG(block.diagram)}</div>
        ${legend ? `<div class="arch-legend">${legend}</div>` : ""}
        ${block.caption ? `<figcaption>${inline(block.caption)}</figcaption>` : ""}
      </figure>`;
    }
    default:
      return "";
  }
}

function renderContent(blocks) {
  return blocks.map(renderBlock).join("");
}

function pathChip(path) {
  return `
    <div class="path-chip">
      ${escapeHtml(path)}
      <button class="copy-button" type="button" data-copy="${escapeHtml(path)}" aria-label="复制路径">${icon("icon-copy")}</button>
    </div>`;
}

/* ---------------- doc view ---------------- */
function renderDocView() {
  const doc = state.docs.find((d) => d.id === state.activeId);
  if (!doc) {
    showHome();
    return;
  }
  els.docIcon.innerHTML = icon(doc.icon || "icon-doc");
  els.docTitle.textContent = doc.title;
  els.docSummary.textContent = doc.summary || "";
  els.docTags.innerHTML = (doc.tags || []).map((t) => `<span class="tag">${t}</span>`).join("");

  const blocks = state.content[doc.id];
  if (blocks && blocks.length) {
    els.docContent.innerHTML = renderContent(blocks);
  } else {
    // fallback for docs whose content hasn't been authored yet
    const signals = (doc.signals || []).map((s) => ({ type: "para", text: s }));
    const details = (doc.details || []).map((s) => ({ type: "para", text: s }));
    const fallback = [
      { type: "callout", text: "本篇内容尚未导入网站，先显示要点摘要。完整正文见对应代码路径下的设计文档。" },
      ...(signals.length ? [{ type: "heading", text: "关键要点" }, ...signals] : []),
      ...(details.length ? [{ type: "heading", text: "补充说明" }, ...details] : []),
    ];
    els.docContent.innerHTML = renderContent(fallback);
  }

  const paths = doc.paths || [];
  if (paths.length) {
    els.docPathsPanel.classList.remove("hidden");
    els.docPaths.innerHTML = paths.map(pathChip).join("");
  } else {
    els.docPathsPanel.classList.add("hidden");
  }
  window.scrollTo(0, 0);
}

/* ---------------- view switching ---------------- */
function showHome() {
  state.view = "home";
  state.activeId = null;
  els.homeView.classList.remove("hidden");
  els.docView.classList.add("hidden");
  renderNav();
  if (state.diagram) renderDiagram(state.diagram);
}

function showDoc(id) {
  state.view = "doc";
  state.activeId = id;
  els.homeView.classList.add("hidden");
  els.docView.classList.remove("hidden");
  renderNav();
  renderDocView();
  closeNav();
}

/* ---------------- mobile drawer ---------------- */
function openNav() {
  document.body.classList.add("nav-open");
}
function closeNav() {
  document.body.classList.remove("nav-open");
}

/* ---------------- clipboard ---------------- */
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

/* ---------------- events ---------------- */
function bindEvents() {
  els.searchInput.addEventListener("input", (event) => {
    state.query = event.target.value.trim();
    renderNav();
  });

  document.querySelectorAll(".filter-button").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".filter-button").forEach((b) => b.classList.remove("active"));
      button.classList.add("active");
      state.filter = button.dataset.filter || "all";
      renderNav();
    });
  });

  els.homeButton.addEventListener("click", () => {
    showHome();
    closeNav();
  });
  els.backButton.addEventListener("click", showHome);

  els.sidebarToggle.addEventListener("click", () =>
    document.body.classList.contains("nav-open") ? closeNav() : openNav()
  );
  els.scrim.addEventListener("click", closeNav);

  document.body.addEventListener("click", async (event) => {
    const copyButton = event.target.closest("[data-copy]");
    if (copyButton) {
      await copyText(copyButton.dataset.copy);
      copyButton.classList.add("copied");
      setTimeout(() => copyButton.classList.remove("copied"), 900);
      return;
    }

    const docButton = event.target.closest("[data-doc-id]");
    if (docButton) {
      showDoc(docButton.dataset.docId);
    }
  });
}

function getPortalData() {
  if (window.DOCS_PORTAL_DATA) return window.DOCS_PORTAL_DATA;
  throw new Error("Docs portal data is missing. Expected assets/portal-data.js to load before portal.js.");
}

function init() {
  Object.assign(els, {
    searchInput: document.querySelector("#searchInput"),
    docNav: document.querySelector("#docNav"),
    homeButton: document.querySelector("#homeButton"),
    backButton: document.querySelector("#backButton"),
    sidebarToggle: document.querySelector("#sidebarToggle"),
    homeView: document.querySelector("#homeView"),
    docView: document.querySelector("#docView"),
    primaryFlow: document.querySelector("#primaryFlow"),
    directoryTree: document.querySelector("#directoryTree"),
    archDiagram: document.querySelector("#archDiagram"),
    docIcon: document.querySelector("#docIcon"),
    docTitle: document.querySelector("#docTitle"),
    docSummary: document.querySelector("#docSummary"),
    docTags: document.querySelector("#docTags"),
    docContent: document.querySelector("#docContent"),
    docPathsPanel: document.querySelector("#docPathsPanel"),
    docPaths: document.querySelector("#docPaths"),
  });

  // backdrop for the mobile drawer
  els.scrim = document.createElement("div");
  els.scrim.className = "scrim";
  document.body.appendChild(els.scrim);

  const manifest = getPortalData();
  state.docs = manifest.documents || [];
  state.diagram = manifest.diagram || null;
  state.content = window.DOCS_PORTAL_CONTENT || {};

  renderFlow(manifest.flow || []);
  renderTree(manifest.tree || "");
  bindEvents();
  showHome();
}

init();
