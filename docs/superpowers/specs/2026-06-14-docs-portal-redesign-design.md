# 文档门户重构设计（2026-06-14）

## 背景

现有 `docs/portal/` 文档门户结构不清晰，主要问题：

1. 同一份文档信息在三处重复展示：左侧导航、中间卡片区、右侧详情栏。
2. 首屏被架构图 + 核心链路 + 数据目录树三块大图堆满，文档被推到下方。
3. 点击行为不统一：点导航、点卡片、点架构图各有不同反应。
4. 文档只有手写摘要，正文要跳转到原 `.md` 才能读。

## 目标

- 架构与文档都要呈现，但分清主次：架构是落地页，文档是下钻。
- 把 md 的**实际内容提取出来，重排成网站原生的结构化板块**（不是嵌入 markdown 阅读器，也不是跳转原文）。
- 消除三处重复列表。

## 方案：主从两栏 + 架构作为首页（方案 C）

布局从三栏改为两栏：

- **左栏（master）= 唯一文档列表**：品牌头 + 搜索框 + 「架构总览」首页入口 + 筛选 chips + 分组文档列表。合并原"导航"和"卡片"为一个列表。
- **右栏（detail）= 单一焦点阅读区**，两种状态：
  - **首页态（默认）**：架构图（主）+ 核心链路 + 数据目录树。
  - **文档态**：标题 + 标签 + 完整结构化正文 + 底部「相关代码路径」（可复制）。顶部有「← 返回架构总览」。

交互统一为一条规则："选中谁，右栏就显示谁"。点列表项、点架构图节点都打开对应文档；点「架构总览」回首页。窄屏左栏收成抽屉。

## 内容模型

新增 `assets/portal-content.js`，按文档 id 存内容块数组：

```js
window.DOCS_PORTAL_CONTENT = {
  "<doc-id>": [ <block>, <block>, ... ],
};
```

块类型（覆盖试点两篇 md 出现的全部元素）：

- `heading` — 小节标题（`{ type, text }`）
- `para` — 段落，正文内联反引号 `code` 自动渲染为 `<code>`
- `list` — 列表（`{ type, ordered?, items: [...] }`）
- `table` — 表格（`{ type, headers: [...], rows: [[...]] }`）
- `code` — 代码块（`{ type, text }`）
- `callout` — 重点框，如"直接结论"（`{ type, title?, text }`）

`portal-data.js` 的架构图/链路/目录树/文档元信息（id、title、group、category、icon、summary、tags、paths）保持不变，作为左栏列表与右栏头部、底部路径的数据源。

## 试点范围

先做两篇内容最丰富的新文档：

- `docx-annotation` ← `DOCX_ANNOTATION_DESIGN.md`
- `review-boundaries` ← `REVIEW_BOUNDARIES.md`

效果满意后，按相同结构补齐其余 7 篇。其余文档在内容缺失时，右栏回退显示其 `summary` + 要点 + 路径（不报错）。

## 文件改动

- `index.html` — 两栏 DOM，删除 inspector 栏和卡片区，加 home/doc 两个视图容器与移动端抽屉开关。
- `assets/portal.css` — 三栏→两栏栅格，home/doc 视图样式，内容块样式，响应式抽屉。
- `assets/portal.js` — 新增 `view: home|doc` 状态切换、统一选中逻辑、`renderContent(blocks)` 块渲染器。
- `assets/portal-data.js` — 元信息不变（本轮已补两篇新文档条目与架构图链接）。
- `assets/portal-content.js` — 新增，试点两篇完整内容。

## 验证

- Node 加载 `portal-data.js` 与 `portal-content.js`，确认语法正确、内容 id 与文档 id 对得上。
- 浏览器打开 `index.html`（`file://`）人工核对两篇文档展示与交互。
