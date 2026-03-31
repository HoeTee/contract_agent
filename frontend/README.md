# 前端说明

当前前端已经围绕“合同审查工作台”这一主路径收敛，不再是早期的演示页集合。

## 当前能力

- 上传合同文件和审查标准文件
- 仅允许在界面中选择 `.pdf` 和 `.docx`
- 选择检索策略并启动审查任务
- 展示任务阶段进度与当前状态
- 左侧查看合同预览
  - PDF 支持浏览器内预览
  - DOCX 不直接预览，服务端会先清洗再解析
- 右侧查看结构化审查结论
  - 按大点/小点组织
  - 展示问题数、风险等级、分析、建议、法律依据
- 切换查看 Markdown 报告
- 下载 `md`、`docx`、`pdf` 报告
- 查看当前后端实例内的历史任务

## 技术栈

- React 18
- TypeScript 5
- Vite 6
- Tailwind CSS
- `react-markdown`
- `remark-gfm`
- `lucide-react`

## 本地开发

### 1. 安装依赖

```powershell
cd frontend
npm install
```

### 2. 配置后端地址

默认推荐：

- 不设置 `VITE_API_URL`
- 直接使用 Vite 开发代理把 `/api` 转发到 `http://localhost:8000`

如果需要显式指定后端地址，在 `frontend/.env` 写入：

```env
VITE_API_URL=http://localhost:8000
```

### 3. 启动开发服务器

```powershell
npm run dev
```

默认地址：

`http://localhost:5173`

### 4. 生产构建

```powershell
npm run build
```

构建产物目录：

`frontend/build`

### 5. 本地预览构建结果

```powershell
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

## 主要页面结构

当前主入口是：

- [`src/App.tsx`](./src/App.tsx)

当前主要功能组件位于：

- [`src/features/contract-review/components/FileDropzone.tsx`](./src/features/contract-review/components/FileDropzone.tsx)
- [`src/features/contract-review/components/DocumentPreview.tsx`](./src/features/contract-review/components/DocumentPreview.tsx)
- [`src/features/contract-review/components/TaskStatusPanel.tsx`](./src/features/contract-review/components/TaskStatusPanel.tsx)
- [`src/features/contract-review/components/HistoryDrawer.tsx`](./src/features/contract-review/components/HistoryDrawer.tsx)
- [`src/services/api.ts`](./src/services/api.ts)

说明：

- `src/features/contract-review/` 是当前主路径
- `src/components/` 下仍有一批旧组件或实验组件，但已经不是当前页面的主实现

## 当前状态模型

任务 `status`：

- `pending`
- `processing`
- `completed`
- `failed`

任务 `stage`：

- `queued`
- `ingesting`
- `building_index`
- `building_tree`
- `planning`
- `reviewing`
- `summarizing`
- `generating_report`
- `completed`
- `failed`

检索模式 `retrieval_mode`：

- `llamaindex`
- `pageindex`
- `evidence`

## 当前限制

- DOCX 在浏览器中不做原文预览
- 历史任务来自后端内存，后端重启后历史会清空
- 前端限制上传 `.pdf` 和 `.docx`，后端上传接口本身没有做同等强校验
- 任务进度目前通过轮询获取，不是 WebSocket 推送
