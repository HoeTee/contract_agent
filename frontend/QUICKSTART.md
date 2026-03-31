# 前端快速开始

这份文档只保留最短启动路径。

## 1. 启动后端

先在项目根目录启动 FastAPI：

```powershell
cd C:\Users\18014\agent_self_practice\deep_research_agent
.\.venv\Scripts\Activate.ps1
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

确认后端正常：

`http://localhost:8000/health`

## 2. 启动前端

打开第二个终端：

```powershell
cd C:\Users\18014\agent_self_practice\deep_research_agent\frontend
npm install
npm run dev
```

打开：

`http://localhost:5173`

## 3. 本地开发默认行为

默认情况下：

- 不需要设置 `VITE_API_URL`
- Vite 会把 `/api` 请求代理到 `http://localhost:8000`

如果你想显式指定后端地址，在 `frontend/.env` 中加入：

```env
VITE_API_URL=http://localhost:8000
```

## 4. 你能在页面上做什么

- 上传合同文件
- 上传审查标准文件
- 选择检索策略
- 启动审查
- 查看阶段进度
- 查看结构化审查结论
- 查看 Markdown 报告
- 下载 `md`、`docx`、`pdf`
- 查看历史任务

## 5. 常见问题

### 页面打不开

检查：

1. 前端是否启动在 `5173`
2. 后端是否启动在 `8000`
3. 浏览器是否访问了 `http://localhost:5173`

### 前端请求失败

检查：

1. `http://localhost:8000/health` 是否正常
2. 是否误配置了 `VITE_API_URL`
3. 后端控制台是否已有报错

### 没有历史任务

当前历史任务保存在后端内存中。页面刷新不影响，但后端重启后会清空。

## 6. 更多说明

- 详细前端说明见 [`README.md`](./README.md)
- 完整部署文档见 [`../DEPLOYMENT.md`](../DEPLOYMENT.md)
