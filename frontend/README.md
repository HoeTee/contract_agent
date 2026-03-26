# 合同审查前端说明

这个前端已经从旧的 demo 形态收敛成真实合同审查工作台。

## 当前能力

- 上传合同文件和审查标准文件
- 启动审查任务并轮询阶段进度
- 左侧查看文档预览
- 右侧查看结构化审查结论
- 右侧切换查看 `Markdown` 报告
- 打开历史任务并重新查看已完成结果
- 下载 `md`、`docx`、`pdf` 报告

## 当前上传限制

- 浏览器 UI 当前只允许选择 `.pdf` 和 `.docx`
- PDF 支持直接预览
- DOCX 会在服务端清洗修订和批注后再解析
- 后端上传接口目前还没有同步做同样的强校验，因此这仍然主要是前端限制

## 技术栈

- React 18
- TypeScript 5
- Vite 6
- Tailwind CSS
- Lucide React
- `react-markdown`

## 本地开发

### 1. 安装依赖

```bash
cd frontend
npm install
```

### 2. 配置后端地址

本地开发推荐：

- 不设置 `VITE_API_URL`
- 直接使用 Vite dev proxy 转发 `/api`

如果你要显式指定后端，请在 `frontend/.env` 中设置：

```env
VITE_API_URL=http://localhost:8000
```

### 3. 启动开发服务器

```bash
npm run dev
```

默认地址：

`http://localhost:5173`

### 4. 构建

```bash
npm run build
```

构建产物目录：

`frontend/build`

### 5. 预览生产构建

```bash
npm run preview
```

## 依赖的后端接口

- `POST /api/v1/upload/contract`
- `POST /api/v1/upload/criteria`
- `POST /api/v1/review/start`
- `GET /api/v1/review/{task_id}`
- `GET /api/v1/review/{task_id}/result`
- `GET /api/v1/review/{task_id}/artifact/{md|docx|pdf}`
- `GET /api/v1/history`
- `GET /api/v1/history/{task_id}`

## 任务模型

`status`：

- `pending`
- `processing`
- `completed`
- `failed`

`stage`：

- `queued`
- `ingesting`
- `building_tree`
- `planning`
- `reviewing`
- `summarizing`
- `generating_report`
- `completed`
- `failed`

## 说明

- 历史任务目前依赖后端内存存储，后端重启后会丢失
- 主界面已经采用“左侧预览，右侧结果”布局
- 右侧结果面板支持风险卡片筛选和 Markdown 渲染
- 当前构建会排除旧的 `src/components` demo 目录，只编译合同审查主路径
