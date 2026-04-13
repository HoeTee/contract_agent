import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Globe,
  LoaderCircle,
  RefreshCw,
  Scale,
  ScanSearch,
  Search,
  TimerReset,
  type LucideIcon,
} from "lucide-react";

import { RetrievalMode, ReviewResultResponse, ReviewStage, ReviewTaskResponse } from "../../../services/api";

interface TaskStatusPanelProps {
  contractFile: File | null;
  criteriaFile: File | null;
  task: ReviewTaskResponse | null;
  result: ReviewResultResponse | null;
  isStarting: boolean;
  error: string | null;
  onStart: (retrievalMode: RetrievalMode, webSearchEnabled: boolean) => void;
  onReset: () => void;
  defaultRetrievalMode: RetrievalMode;
  defaultWebSearchEnabled: boolean;
}

type StageState = "pending" | "active" | "complete";

type Strategy = {
  id: RetrievalMode;
  label: string;
  subtitle: string;
  description: string;
  speed: string;
  coverage: string;
  icon: LucideIcon;
  accent: string;
  active: string;
  chip: string;
  beta?: boolean;
};

const STRATEGIES: Strategy[] = [
  {
    id: "llamaindex",
    label: "快速检索",
    subtitle: "LlamaIndex",
    description: "优先强调速度与快速定位，适合尽快得到相关上下文。",
    speed: "速度最快",
    coverage: "覆盖基础",
    icon: Search,
    accent: "border-brand-100 bg-brand-50 text-brand-700",
    active: "border-brand-300 bg-brand-50/90 shadow-soft",
    chip: "border-brand-100 bg-brand-50 text-brand-800",
  },
  {
    id: "pageindex",
    label: "智能检索",
    subtitle: "PageIndex",
    description: "强调结构理解与层级定位，适合长文档中的关系检索。",
    speed: "速度平衡",
    coverage: "结构理解",
    icon: ScanSearch,
    accent: "border-trust-100 bg-trust-50 text-trust-700",
    active: "border-trust-300 bg-trust-50/90 shadow-soft",
    chip: "border-trust-100 bg-trust-50 text-trust-800",
    beta: true,
  },
  {
    id: "evidence",
    label: "全面核查",
    subtitle: "Evidence Collector",
    description: "按标准逐项收集证据，覆盖最全，更适合细致的审查场景。",
    speed: "耗时更长",
    coverage: "覆盖最全",
    icon: Scale,
    accent: "border-slate-200 bg-slate-100 text-slate-700",
    active: "border-slate-300 bg-slate-100/90 shadow-soft",
    chip: "border-slate-200 bg-slate-100 text-slate-700",
    beta: true,
  },
];

function formatTime(value?: string | null) {
  if (!value) return "未开始";
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function statusMeta(status?: string | null) {
  switch (status) {
    case "processing":
      return { label: "处理中", tone: "border-brand-100 bg-brand-50 text-brand-800" };
    case "completed":
      return { label: "已完成", tone: "border-trust-100 bg-trust-50 text-trust-800" };
    case "failed":
      return { label: "失败", tone: "border-rose-200 bg-rose-50 text-rose-700" };
    case "pending":
      return { label: "待处理", tone: "border-slate-200 bg-slate-100 text-slate-700" };
    default:
      return { label: "未启动", tone: "border-slate-200 bg-slate-100 text-slate-700" };
  }
}

function stageState(stages: Array<{ id: ReviewStage }>, activeStage: ReviewStage | null | undefined, current: ReviewStage): StageState {
  const activeIndex = stages.findIndex((stage) => stage.id === (activeStage || "queued"));
  const currentIndex = stages.findIndex((stage) => stage.id === current);
  if (activeIndex === -1 || currentIndex === -1) return "pending";
  if (currentIndex < activeIndex) return "complete";
  if (currentIndex === activeIndex) return "active";
  return "pending";
}

export function TaskStatusPanel(props: TaskStatusPanelProps) {
  const {
    contractFile,
    criteriaFile,
    task,
    result,
    isStarting,
    error,
    onStart,
    onReset,
    defaultRetrievalMode,
    defaultWebSearchEnabled,
  } = props;

  const [retrievalMode, setRetrievalMode] = useState<RetrievalMode>(defaultRetrievalMode);
  const [webSearchEnabled, setWebSearchEnabled] = useState(defaultWebSearchEnabled);

  const activeStage = result?.stage || task?.stage;
  const currentStatus = task?.status || result?.status;
  const currentStatusMeta = statusMeta(currentStatus);
  const canStart = Boolean(contractFile && criteriaFile) && !isStarting && task?.status !== "processing";
  const taskId = result?.task_id || task?.task_id;
  const progressMessage = task?.progress_message || result?.progress_message;
  const currentStrategy = STRATEGIES.find((item) => item.id === retrievalMode) || STRATEGIES[0];

  useEffect(() => {
    setRetrievalMode(result?.retrieval_mode || task?.retrieval_mode || defaultRetrievalMode);
  }, [defaultRetrievalMode, result?.retrieval_mode, task?.retrieval_mode]);

  useEffect(() => {
    setWebSearchEnabled(result?.web_search_enabled ?? task?.web_search_enabled ?? defaultWebSearchEnabled);
  }, [defaultWebSearchEnabled, result?.web_search_enabled, task?.web_search_enabled]);

  const phaseTwo = activeStage === "building_index" ? "building_index" : retrievalMode === "llamaindex" ? "building_index" : "building_tree";
  const stages: Array<{ id: ReviewStage; label: string }> = [
    { id: "queued", label: "任务已创建" },
    { id: "ingesting", label: "解析文件" },
    { id: phaseTwo, label: phaseTwo === "building_index" ? "构建 LlamaIndex 索引" : "构建 PageIndex 结构树" },
    { id: "planning", label: "提取审查标准" },
    { id: "reviewing", label: "执行审查" },
    { id: "summarizing", label: "汇总结论" },
    { id: "generating_report", label: "生成报告" },
    { id: "completed", label: "已完成" },
  ];

  return (
    <section className="surface-panel p-5 text-slate-900">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="eyebrow">Task Console</p>
          <h2 className="mt-2 font-serif text-3xl font-semibold text-slate-950">合同审查工作台</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">这里集中显示任务状态、检索策略、联网搜索开关和执行进度。审查结论将作为下方的独立板块展示。</p>
        </div>
        <div className="rounded-[22px] border border-brand-100 bg-brand-50 p-3 text-brand-700">
          <Scale className="h-6 w-6" />
        </div>
      </div>

      <div className="mt-5 grid gap-4">
        <div className="surface-subtle grid gap-3 p-4">
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className="text-slate-500">合同文件</span>
            <span className="max-w-[65%] truncate text-right font-medium text-slate-800">{contractFile?.name || task?.contract_name || "-"}</span>
          </div>
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className="text-slate-500">审查标准</span>
            <span className="max-w-[65%] truncate text-right font-medium text-slate-800">{criteriaFile?.name || "-"}</span>
          </div>
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className="text-slate-500">Task ID</span>
            <span className="max-w-[65%] truncate text-right font-mono text-xs text-slate-700">{taskId || "-"}</span>
          </div>
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className="text-slate-500">状态</span>
            <span className={`rounded-full border px-3 py-1 text-xs font-medium ${currentStatusMeta.tone}`}>{currentStatusMeta.label}</span>
          </div>
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className="text-slate-500">开始时间</span>
            <span className="text-slate-700">{formatTime(task?.created_at || result?.created_at)}</span>
          </div>
        </div>

        <div className="surface-subtle p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="eyebrow">Retrieval Strategy</p>
              <h3 className="mt-2 text-lg font-semibold text-slate-900">检索策略</h3>
              <p className="mt-2 text-sm leading-6 text-slate-600">用于决定审查时如何从合同中定位证据与上下文，不同模式在速度、覆盖和结构理解上侧重点不同。</p>
            </div>
            <span className={`rounded-full border px-3 py-1 text-xs font-medium ${currentStrategy.chip}`}>当前选择：{currentStrategy.label}</span>
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-3">
            {STRATEGIES.map((item) => {
              const Icon = item.icon;
              const active = retrievalMode === item.id;

              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setRetrievalMode(item.id)}
                  className={`rounded-[22px] border bg-white/90 p-4 text-left transition ${
                    active ? item.active : "border-slate-200 hover:border-brand-200 hover:bg-brand-50/40"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className={`flex h-11 w-11 items-center justify-center rounded-2xl border ${item.accent}`}>
                      <Icon className="h-5 w-5" />
                    </div>
                    {item.beta ? (
                      <span className="rounded-full border border-trust-100 bg-trust-50 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-trust-800">
                        Beta
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-4 text-sm font-semibold text-slate-900">{item.label}</p>
                  <p className="mt-1 text-xs font-medium uppercase tracking-[0.18em] text-slate-500">{item.subtitle}</p>
                  <p className="mt-3 text-sm leading-6 text-slate-600">{item.description}</p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-600">{item.speed}</span>
                    <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-600">{item.coverage}</span>
                  </div>
                </button>
              );
            })}
          </div>

          <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_280px]">
            <div className="rounded-[20px] border border-slate-200 bg-white/90 px-4 py-3 text-xs leading-6 text-slate-600">
              当前选择会作为本次任务的检索策略提交给服务端；历史任务会回显其实际执行模式。联网搜索默认值来自 `ENABLE_WEB_SEACH_TOOL`，点击开关后只覆盖本次任务，不会改动服务端 `.env`。
            </div>
            <button
              type="button"
              onClick={() => setWebSearchEnabled((value) => !value)}
              className={`rounded-[20px] border px-4 py-4 text-left transition ${
                webSearchEnabled
                  ? "border-brand-300 bg-brand-50 text-brand-900"
                  : "border-slate-200 bg-white text-slate-700 hover:border-brand-200 hover:bg-brand-50/40"
              }`}
              aria-pressed={webSearchEnabled}
            >
              <div className="flex items-start justify-between gap-3">
                <div className={`flex h-11 w-11 items-center justify-center rounded-2xl border ${
                  webSearchEnabled ? "border-brand-200 bg-white text-brand-700" : "border-slate-200 bg-slate-50 text-slate-500"
                }`}>
                  <Globe className="h-5 w-5" />
                </div>
                <span className={`rounded-full px-3 py-1 text-xs font-semibold ${
                  webSearchEnabled ? "bg-brand-700 text-white" : "bg-slate-100 text-slate-600"
                }`}>
                  {webSearchEnabled ? "已开启" : "已关闭"}
                </span>
              </div>
              <h4 className="mt-4 text-sm font-semibold">联网搜索</h4>
              <p className="mt-2 text-sm leading-6">
                开启后，审查代理可在允许的范围内调用网页搜索与页面读取工具，用于补充法律法规和行业惯例依据。
              </p>
            </button>
          </div>
        </div>

        <div className="surface-subtle p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="eyebrow">Progress</p>
              <h3 className="mt-2 text-lg font-semibold text-slate-900">流程进度</h3>
            </div>
            <span className={`rounded-full border px-3 py-1 text-xs font-medium ${currentStatusMeta.tone}`}>{currentStatusMeta.label}</span>
          </div>

          <div className="mt-4 space-y-2" aria-live="polite">
            {stages.map((stage) => {
              const state = task?.status === "failed" ? "pending" : stageState(stages, activeStage, stage.id);
              const tone =
                state === "complete"
                  ? "border-trust-200 bg-trust-50 text-trust-800"
                  : state === "active"
                    ? "border-brand-200 bg-brand-50 text-brand-800"
                    : "border-slate-200 bg-white text-slate-400";

              return (
                <div key={stage.id} className={`flex items-center gap-3 rounded-2xl border px-3 py-3 ${tone}`}>
                  <div className={`h-2.5 w-2.5 rounded-full ${
                    state === "complete" ? "bg-trust-500" : state === "active" ? "bg-brand-600" : "bg-slate-300"
                  }`}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{stage.label}</p>
                    {activeStage === stage.id && progressMessage ? <p className="mt-0.5 truncate text-xs text-current/80">{progressMessage}</p> : null}
                  </div>
                  {state === "active" ? <LoaderCircle className="h-4 w-4 animate-spin" /> : null}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {task?.status === "failed" || error ? (
        <div className="mt-5 rounded-[24px] border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700" role="alert">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-none" />
            <div>
              <p className="font-medium">审查失败</p>
              <p className="mt-2 leading-6">{error || task?.error}</p>
            </div>
          </div>
        </div>
      ) : null}

      <div className="mt-5 flex flex-wrap gap-3">
        <button type="button" onClick={() => onStart(retrievalMode, webSearchEnabled)} disabled={!canStart} className="action-primary">
          {isStarting || task?.status === "processing" ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          {task?.status === "processing" ? "审查进行中" : "开始审查"}
        </button>

        <button type="button" onClick={onReset} className="action-secondary">
          <TimerReset className="h-4 w-4" />
          重置工作台
        </button>
      </div>
    </section>
  );
}
