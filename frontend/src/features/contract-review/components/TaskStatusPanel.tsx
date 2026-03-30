import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ChevronRight,
  Download,
  FileCode2,
  FileSearch,
  LoaderCircle,
  RefreshCw,
  Scale,
  ScanSearch,
  Search,
  ShieldAlert,
  ShieldCheck,
  ShieldQuestion,
  TimerReset,
  type LucideIcon,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  Issue,
  RetrievalMode,
  ReviewResultResponse,
  ReviewStage,
  ReviewTaskResponse,
  getReviewArtifactText,
  getReviewArtifactUrl,
} from "../../../services/api";

interface TaskStatusPanelProps {
  contractFile: File | null;
  criteriaFile: File | null;
  task: ReviewTaskResponse | null;
  result: ReviewResultResponse | null;
  isStarting: boolean;
  error: string | null;
  onStart: (retrievalMode: RetrievalMode) => void;
  onReset: () => void;
}

type ResultTab = "issues" | "markdown";
type RiskFilter = "all" | Issue["risk_level"];
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
  },
];

function issueKey(issue: Issue, index: number) {
  return `${index}-${issue.violated_criteria}-${issue.clause_location}`;
}

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

function riskMeta(level: Issue["risk_level"]) {
  switch (level) {
    case "high":
      return { label: "高风险", tone: "border-rose-200 bg-rose-50 text-rose-700", badge: "bg-rose-100 text-rose-700" };
    case "medium":
      return { label: "中风险", tone: "border-amber-200 bg-amber-50 text-amber-700", badge: "bg-amber-100 text-amber-700" };
    case "low":
      return { label: "低风险", tone: "border-sky-200 bg-sky-50 text-sky-700", badge: "bg-sky-100 text-sky-700" };
    default:
      return { label: "无风险", tone: "border-emerald-200 bg-emerald-50 text-emerald-700", badge: "bg-emerald-100 text-emerald-700" };
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
  const { contractFile, criteriaFile, task, result, isStarting, error, onStart, onReset } = props;
  const [activeTab, setActiveTab] = useState<ResultTab>("issues");
  const [riskFilter, setRiskFilter] = useState<RiskFilter>("all");
  const [selectedIssueKey, setSelectedIssueKey] = useState<string | null>(null);
  const [markdownContent, setMarkdownContent] = useState("");
  const [markdownError, setMarkdownError] = useState<string | null>(null);
  const [isLoadingMarkdown, setIsLoadingMarkdown] = useState(false);
  const [retrievalMode, setRetrievalMode] = useState<RetrievalMode>("llamaindex");

  const activeStage = result?.stage || task?.stage;
  const currentStatus = task?.status || result?.status;
  const currentStatusMeta = statusMeta(currentStatus);
  const canStart = Boolean(contractFile && criteriaFile) && !isStarting && task?.status !== "processing";
  const taskId = result?.task_id || task?.task_id;
  const progressMessage = task?.progress_message || result?.progress_message;

  const issues = useMemo(
    () => (result?.issues || []).map((issue, index) => ({ issue, index, key: issueKey(issue, index) })),
    [result],
  );

  const filteredIssues = issues.filter((entry) => (riskFilter === "all" ? true : entry.issue.risk_level === riskFilter));
  const selectedIssue = filteredIssues.find((entry) => entry.key === selectedIssueKey) || filteredIssues[0] || null;
  const currentStrategy = STRATEGIES.find((item) => item.id === retrievalMode) || STRATEGIES[0];

  useEffect(() => {
    const nextMode = result?.retrieval_mode || task?.retrieval_mode;
    if (nextMode) {
      setRetrievalMode(nextMode);
      return;
    }

    if (activeStage === "building_index") {
      setRetrievalMode("llamaindex");
    }
  }, [activeStage, result?.retrieval_mode, task?.retrieval_mode]);

  useEffect(() => {
    if (!result) {
      setRiskFilter("all");
      setSelectedIssueKey(null);
      setMarkdownContent("");
      setMarkdownError(null);
      setActiveTab("issues");
      return;
    }

    setRiskFilter("all");
    setSelectedIssueKey(result.issues[0] ? issueKey(result.issues[0], 0) : null);

    let cancelled = false;
    setIsLoadingMarkdown(true);
    setMarkdownError(null);

    getReviewArtifactText(result.task_id, "md")
      .then((content) => {
        if (!cancelled) setMarkdownContent(content);
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setMarkdownError(reason instanceof Error ? reason.message : "Markdown 报告加载失败");
          setMarkdownContent("");
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoadingMarkdown(false);
      });

    return () => {
      cancelled = true;
    };
  }, [result]);

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

  const riskCounts = {
    high: result?.issues.filter((item) => item.risk_level === "high").length || 0,
    medium: result?.issues.filter((item) => item.risk_level === "medium").length || 0,
    low: result?.issues.filter((item) => item.risk_level === "low").length || 0,
    none: result?.issues.filter((item) => item.risk_level === "none").length || 0,
  };

  const summaryCards = [
    {
      id: "all" as const,
      label: "全部问题",
      value: result?.total_issues || 0,
      icon: FileSearch,
      tone: "border-slate-200 bg-slate-50 text-slate-700",
      active: "border-slate-400 bg-slate-100 text-slate-900 shadow-soft",
    },
    {
      id: "high" as const,
      label: "高风险",
      value: riskCounts.high,
      icon: ShieldAlert,
      tone: "border-rose-200 bg-rose-50 text-rose-700",
      active: "border-rose-400 bg-rose-100 text-rose-900 shadow-soft",
    },
    {
      id: "medium" as const,
      label: "中风险",
      value: riskCounts.medium,
      icon: AlertTriangle,
      tone: "border-amber-200 bg-amber-50 text-amber-700",
      active: "border-amber-400 bg-amber-100 text-amber-900 shadow-soft",
    },
    {
      id: "low" as const,
      label: "低风险",
      value: riskCounts.low,
      icon: ShieldQuestion,
      tone: "border-sky-200 bg-sky-50 text-sky-700",
      active: "border-sky-400 bg-sky-100 text-sky-900 shadow-soft",
    },
    {
      id: "none" as const,
      label: "无风险",
      value: riskCounts.none,
      icon: ShieldCheck,
      tone: "border-emerald-200 bg-emerald-50 text-emerald-700",
      active: "border-emerald-400 bg-emerald-100 text-emerald-900 shadow-soft",
    },
  ];

  return (
    <section className="surface-panel p-5 text-slate-900">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="eyebrow">Task Console</p>
          <h2 className="mt-2 font-serif text-3xl font-semibold text-slate-950">合同审查工作台</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">这里集中显示任务状态、策略入口、问题详情与 Markdown 审查报告。</p>
        </div>
        <div className="rounded-[22px] border border-brand-100 bg-brand-50 p-3 text-brand-700">
          <Scale className="h-6 w-6" />
        </div>
      </div>

      <div className="mt-5 grid gap-4">
        <div className="surface-subtle grid gap-3 p-4">
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className="text-slate-500">合同文件</span>
            <span className="max-w-[65%] truncate text-right font-medium text-slate-800">
              {contractFile?.name || task?.contract_name || "-"}
            </span>
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
              <p className="mt-2 text-sm leading-6 text-slate-600">按最新链路展示三种策略入口，帮助用户理解速度、结构理解与覆盖深度的差异。</p>
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

          <div className="mt-4 rounded-[20px] border border-slate-200 bg-white/90 px-4 py-3 text-xs leading-6 text-slate-600">
            当前选择会作为本次任务的检索策略提交给服务端；历史任务会回显其实际执行模式。
          </div>

          <div className="hidden">
            实际执行策略仍由服务端当前配置决定。当前选择用于前端展示与操作提示，不会修改后端检索链路。
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
                  <div
                    className={`h-2.5 w-2.5 rounded-full ${
                      state === "complete" ? "bg-trust-500" : state === "active" ? "bg-brand-600" : "bg-slate-300"
                    }`}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{stage.label}</p>
                    {activeStage === stage.id && progressMessage ? (
                      <p className="mt-0.5 truncate text-xs text-current/80">{progressMessage}</p>
                    ) : null}
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
        <button type="button" onClick={() => onStart(retrievalMode)} disabled={!canStart} className="action-primary">
          {isStarting || task?.status === "processing" ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          {task?.status === "processing" ? "审查进行中" : "开始审查"}
        </button>

        <button type="button" onClick={onReset} className="action-secondary">
          <TimerReset className="h-4 w-4" />
          重置工作台
        </button>
      </div>

      <div className="mt-6 rounded-[28px] border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="eyebrow">Results</p>
            <h3 className="mt-2 text-xl font-semibold text-slate-900">审查结论</h3>
            <p className="mt-2 text-sm text-slate-600">
              {result ? `已生成 ${result.total_issues} 条问题记录，可切换查看结构化结论或 Markdown 报告。` : "任务完成后，这里会显示风险分布、问题卡片和 Markdown 报告。"}
            </p>
          </div>
          {result ? (
            <div className="flex flex-wrap gap-2">
              {(["md", "docx", "pdf"] as const).map((artifact) => (
                <a
                  key={artifact}
                  href={getReviewArtifactUrl(result.task_id, artifact)}
                  className="inline-flex items-center gap-2 rounded-full border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 transition hover:border-brand-300 hover:bg-brand-50 hover:text-brand-900"
                  target="_blank"
                  rel="noreferrer"
                >
                  <Download className="h-4 w-4" />
                  {artifact.toUpperCase()}
                </a>
              ))}
            </div>
          ) : null}
        </div>

        <div className="mt-4 inline-flex rounded-full border border-slate-200 bg-slate-50 p-1">
          <button
            type="button"
            onClick={() => setActiveTab("issues")}
            className={`rounded-full px-4 py-2 text-sm font-medium transition ${activeTab === "issues" ? "bg-brand-700 text-white" : "text-slate-600 hover:text-slate-900"}`}
          >
            结构化结论
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("markdown")}
            className={`rounded-full px-4 py-2 text-sm font-medium transition ${activeTab === "markdown" ? "bg-brand-700 text-white" : "text-slate-600 hover:text-slate-900"}`}
          >
            Markdown 报告
          </button>
        </div>

        {activeTab === "issues" ? (
          result ? (
            <div className="mt-5 space-y-4">
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {summaryCards.map((card) => (
                  <button
                    key={card.id}
                    type="button"
                    onClick={() => {
                      setRiskFilter(card.id);
                      const next = issues.find((entry) => card.id === "all" || entry.issue.risk_level === card.id);
                      setSelectedIssueKey(next?.key || null);
                    }}
                    className={`rounded-[22px] border px-4 py-3 text-left transition ${riskFilter === card.id ? card.active : card.tone}`}
                  >
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-medium">{card.label}</p>
                      <card.icon className="h-4 w-4" />
                    </div>
                    <p className="mt-3 text-2xl font-semibold">{card.value}</p>
                  </button>
                ))}
              </div>

              <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
                <div className="rounded-[24px] border border-slate-200 bg-slate-50 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-medium text-slate-700">当前筛选：{summaryCards.find((card) => card.id === riskFilter)?.label}</p>
                    <span className="text-xs text-slate-500">{filteredIssues.length} 条</span>
                  </div>

                  {filteredIssues.length === 0 ? (
                    <div className="mt-3 rounded-2xl border border-dashed border-slate-200 bg-white px-4 py-6 text-sm text-slate-500">
                      当前风险级别下没有可显示的问题。
                    </div>
                  ) : (
                    <div className="mt-3 max-h-72 space-y-2 overflow-y-auto pr-1">
                      {filteredIssues.map((entry) => {
                        const risk = riskMeta(entry.issue.risk_level);
                        const active = selectedIssue?.key === entry.key;

                        return (
                          <button
                            key={entry.key}
                            type="button"
                            onClick={() => setSelectedIssueKey(entry.key)}
                            className={`w-full rounded-[20px] border px-4 py-3 text-left transition ${
                              active ? "border-brand-300 bg-brand-50 shadow-soft" : "border-slate-200 bg-white hover:border-brand-200 hover:bg-brand-50/50"
                            }`}
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <p className="truncate text-sm font-semibold text-slate-800">{entry.issue.violated_criteria || `问题 ${entry.index + 1}`}</p>
                                <p className="mt-1 truncate text-xs text-slate-500">{entry.issue.clause_location || "未提供条款位置"}</p>
                              </div>
                              <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${risk.badge}`}>{risk.label}</span>
                            </div>
                            <p className="mt-2 line-clamp-2 text-sm leading-6 text-slate-600">{entry.issue.conclusion || "未提供结论"}</p>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>

                {selectedIssue ? (
                  <article className="rounded-[24px] border border-brand-100 bg-white p-4 shadow-soft">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="eyebrow">Issue Detail</p>
                        <h4 className="mt-2 text-lg font-semibold text-slate-900">{selectedIssue.issue.violated_criteria || `问题 ${selectedIssue.index + 1}`}</h4>
                      </div>
                      <span className={`rounded-full px-3 py-1 text-xs font-medium ${riskMeta(selectedIssue.issue.risk_level).badge}`}>
                        {riskMeta(selectedIssue.issue.risk_level).label}
                      </span>
                    </div>

                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      <div className="rounded-[18px] border border-slate-200 bg-slate-50 px-4 py-3">
                        <p className="text-xs font-semibold tracking-[0.18em] text-slate-500">条款位置</p>
                        <p className="mt-2 text-sm leading-6 text-slate-700">{selectedIssue.issue.clause_location || "未提供"}</p>
                      </div>
                      <div className="rounded-[18px] border border-slate-200 bg-slate-50 px-4 py-3">
                        <p className="text-xs font-semibold tracking-[0.18em] text-slate-500">页码</p>
                        <p className="mt-2 text-sm leading-6 text-slate-700">{selectedIssue.issue.page || "未提供"}</p>
                      </div>
                    </div>

                    <div className="mt-3 space-y-3">
                      {[
                        ["结论", selectedIssue.issue.conclusion || "未提供"],
                        ["分析", selectedIssue.issue.analysis || "未提供"],
                        ["修改建议", selectedIssue.issue.suggestion || "未提供"],
                        ["法律依据", selectedIssue.issue.legal_basis || "未提供"],
                      ].map(([label, value]) => (
                        <div key={label} className="rounded-[18px] border border-slate-200 bg-slate-50 px-4 py-3">
                          <p className="text-xs font-semibold tracking-[0.18em] text-slate-500">{label}</p>
                          <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">{value}</p>
                        </div>
                      ))}
                    </div>
                  </article>
                ) : null}
              </div>
            </div>
          ) : (
            <div className="mt-5 rounded-[24px] border border-dashed border-slate-200 bg-slate-50 px-5 py-8 text-center text-sm text-slate-500">
              审查完成后，这里会显示可点击的风险卡片和问题详情。
            </div>
          )
        ) : (
          <div className="mt-5 rounded-[24px] border border-slate-200 bg-slate-50 p-4">
            {isLoadingMarkdown ? (
              <div className="flex items-center gap-3 text-sm text-slate-600" role="status" aria-live="polite">
                <LoaderCircle className="h-4 w-4 animate-spin" />
                正在加载 Markdown 报告...
              </div>
            ) : markdownError ? (
              <div className="rounded-[20px] border border-rose-200 bg-rose-50 px-4 py-5 text-sm text-rose-700" role="alert">
                {markdownError}
              </div>
            ) : markdownContent ? (
              <div className="max-h-[900px] overflow-y-auto pr-1">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    h1: (p) => <h1 className="mt-6 font-serif text-3xl font-semibold text-slate-950 first:mt-0" {...p} />,
                    h2: (p) => <h2 className="mt-5 border-b border-slate-200 pb-2 text-xl font-semibold text-slate-900" {...p} />,
                    h3: (p) => <h3 className="mt-4 text-lg font-semibold text-slate-800" {...p} />,
                    p: (p) => <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-700 first:mt-0" {...p} />,
                    ul: (p) => <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-7 text-slate-700" {...p} />,
                    ol: (p) => <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm leading-7 text-slate-700" {...p} />,
                    li: (p) => <li className="marker:text-brand-600" {...p} />,
                    blockquote: (p) => <blockquote className="mt-4 rounded-r-2xl border-l-4 border-brand-300 bg-brand-50 px-4 py-3 text-sm leading-7 text-slate-700" {...p} />,
                    code: ({ className, children, ...p }) =>
                      className ? <code className={className} {...p}>{children}</code> : <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[13px] text-brand-800" {...p}>{children}</code>,
                    pre: (p) => <pre className="mt-4 overflow-x-auto rounded-[20px] border border-slate-200 bg-slate-950 px-4 py-4 text-[13px] leading-6 text-slate-100" {...p} />,
                    table: (p) => <div className="mt-4 overflow-x-auto rounded-[20px] border border-slate-200 bg-white"><table className="min-w-full border-collapse text-left text-sm text-slate-700" {...p} /></div>,
                    th: (p) => <th className="border-b border-slate-200 bg-slate-50 px-3 py-2 font-semibold text-slate-800" {...p} />,
                    td: (p) => <td className="border-b border-slate-100 px-3 py-2 align-top" {...p} />,
                    a: (p) => <a className="text-brand-700 underline underline-offset-4" {...p} />,
                    hr: (p) => <hr className="my-6 border-slate-200" {...p} />,
                  }}
                >
                  {markdownContent}
                </ReactMarkdown>
              </div>
            ) : (
              <div className="flex items-center gap-3 text-sm text-slate-500">
                <FileCode2 className="h-4 w-4" />
                当前没有可展示的 Markdown 报告。
              </div>
            )}
          </div>
        )}

        {result?.completed_at ? (
          <div className="mt-4 flex items-center gap-2 text-xs text-slate-500">
            <ChevronRight className="h-3.5 w-3.5" />
            完成时间：{formatTime(result.completed_at)}
          </div>
        ) : null}
      </div>
    </section>
  );
}
