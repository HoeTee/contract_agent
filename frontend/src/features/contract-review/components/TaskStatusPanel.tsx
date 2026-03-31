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
  TimerReset,
  type LucideIcon,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  Issue,
  RetrievalMode,
  ReviewItem,
  ReviewItemStatus,
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

type ResultTab = "structured" | "markdown";
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

type ReviewSectionGroup = {
  section: string;
  items: ReviewItem[];
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

function reviewItemKey(item: ReviewItem) {
  return item.criterion_id || `${item.section}-${item.criterion}`;
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
      return { label: "高风险", badge: "bg-rose-100 text-rose-700" };
    case "medium":
      return { label: "中风险", badge: "bg-amber-100 text-amber-700" };
    case "low":
      return { label: "低风险", badge: "bg-sky-100 text-sky-700" };
    default:
      return { label: "无风险", badge: "bg-emerald-100 text-emerald-700" };
    }
}

function reviewItemStatusMeta(status: ReviewItemStatus) {
  switch (status) {
    case "compliant":
      return { label: "已通过", tone: "border-emerald-200 bg-emerald-50 text-emerald-700" };
    case "error":
      return { label: "执行异常", tone: "border-rose-200 bg-rose-50 text-rose-700" };
    default:
      return { label: "发现问题", tone: "border-amber-200 bg-amber-50 text-amber-700" };
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

function getHighestRiskLevel(issues: Issue[]): Issue["risk_level"] | null {
  if (issues.some((issue) => issue.risk_level === "high")) return "high";
  if (issues.some((issue) => issue.risk_level === "medium")) return "medium";
  if (issues.some((issue) => issue.risk_level === "low")) return "low";
  if (issues.some((issue) => issue.risk_level === "none")) return "none";
  return null;
}

function buildFallbackReviewItems(issues: Issue[]): ReviewItem[] {
  const grouped = new Map<string, ReviewItem>();

  issues.forEach((issue, index) => {
    const section = issue.section || "未分组";
    const criterion = issue.criterion || issue.violated_criteria || `问题 ${index + 1}`;
    const criterionId = issue.criterion_id || `legacy-${index + 1}`;
    const key = `${section}-${criterion}`;
    const current = grouped.get(key);

    if (current) {
      current.issues.push(issue);
      current.issue_count = current.issues.length;
      return;
    }

    grouped.set(key, {
      criterion_id: criterionId,
      section,
      criterion,
      status: "issues_found",
      issue_count: 1,
      issues: [issue],
    });
  });

  return Array.from(grouped.values());
}

function groupReviewItems(items: ReviewItem[]): ReviewSectionGroup[] {
  const groups = new Map<string, ReviewSectionGroup>();

  items.forEach((item) => {
    const section = item.section || "其他";
    const current = groups.get(section);
    if (current) {
      current.items.push(item);
      return;
    }

    groups.set(section, { section, items: [item] });
  });

  return Array.from(groups.values());
}

export function TaskStatusPanel(props: TaskStatusPanelProps) {
  const { contractFile, criteriaFile, task, result, isStarting, error, onStart, onReset } = props;
  const [activeTab, setActiveTab] = useState<ResultTab>("structured");
  const [selectedReviewItemKey, setSelectedReviewItemKey] = useState<string | null>(null);
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
  const reviewItems = useMemo(() => {
    if (!result) return [];
    return result.review_items?.length ? result.review_items : buildFallbackReviewItems(result.issues || []);
  }, [result]);
  const groupedReviewItems = useMemo(() => groupReviewItems(reviewItems), [reviewItems]);
  const selectedReviewItem = reviewItems.find((item) => reviewItemKey(item) === selectedReviewItemKey) || reviewItems[0] || null;
  const currentStrategy = STRATEGIES.find((item) => item.id === retrievalMode) || STRATEGIES[0];
  const structuredStats = useMemo(
    () => ({
      total: reviewItems.length,
      issuesFound: reviewItems.filter((item) => item.status === "issues_found").length,
      compliant: reviewItems.filter((item) => item.status === "compliant").length,
      error: reviewItems.filter((item) => item.status === "error").length,
    }),
    [reviewItems],
  );

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
      setSelectedReviewItemKey(null);
      setMarkdownContent("");
      setMarkdownError(null);
      setActiveTab("structured");
      return;
    }

    const initialItem = result.review_items?.[0] || buildFallbackReviewItems(result.issues || [])[0];
    setSelectedReviewItemKey(initialItem ? reviewItemKey(initialItem) : null);

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

  const summaryCards = [
    {
      label: "审查要点",
      value: structuredStats.total,
      icon: FileSearch,
      tone: "border-slate-200 bg-slate-50 text-slate-700",
    },
    {
      label: "发现问题",
      value: structuredStats.issuesFound,
      icon: ShieldAlert,
      tone: "border-amber-200 bg-amber-50 text-amber-700",
    },
    {
      label: "已通过",
      value: structuredStats.compliant,
      icon: ShieldCheck,
      tone: "border-emerald-200 bg-emerald-50 text-emerald-700",
    },
    {
      label: "执行异常",
      value: structuredStats.error,
      icon: AlertTriangle,
      tone: "border-rose-200 bg-rose-50 text-rose-700",
    },
  ];

  return (
    <section className="surface-panel p-5 text-slate-900">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="eyebrow">Task Console</p>
          <h2 className="mt-2 font-serif text-3xl font-semibold text-slate-950">合同审查工作台</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">这里集中显示任务状态、策略入口、按审查要点组织的结构化结论，以及 Markdown 审查报告。</p>
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

          <div className="mt-4 rounded-[20px] border border-slate-200 bg-white/90 px-4 py-3 text-xs leading-6 text-slate-600">
            当前选择会作为本次任务的检索策略提交给服务端；历史任务会回显其实际执行模式。
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
              {result
                ? `已按 ${structuredStats.total} 个审查要点组织结果，其中 ${structuredStats.issuesFound} 个要点发现问题，共提取 ${result.total_issues} 条结构化问题。`
                : "任务完成后，这里会按审查大点和小点展示结论，并保留 Markdown 报告查看入口。"}
            </p>
          </div>
          {result ? (
            <div className="flex flex-wrap gap-2">
              {(["md", "docx", "pdf"] as const)
                .filter((artifact) => {
                  const key = `report_${artifact}` as keyof typeof result;
                  return result[key];
                })
                .map((artifact) => (
                <a
                  key={artifact}
                  href={getReviewArtifactUrl(result.task_id, artifact)}
                  download
                  className="inline-flex items-center gap-2 rounded-full border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 transition hover:border-brand-300 hover:bg-brand-50 hover:text-brand-900"
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
            onClick={() => setActiveTab("structured")}
            className={`rounded-full px-4 py-2 text-sm font-medium transition ${activeTab === "structured" ? "bg-brand-700 text-white" : "text-slate-600 hover:text-slate-900"}`}
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

        {activeTab === "structured" ? (
          result ? (
            <div className="mt-5 space-y-4">
              <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-4">
                {summaryCards.map((card) => (
                  <div key={card.label} className={`rounded-[22px] border px-4 py-3 ${card.tone}`}>
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-medium">{card.label}</p>
                      <card.icon className="h-4 w-4" />
                    </div>
                    <p className="mt-3 text-2xl font-semibold">{card.value}</p>
                  </div>
                ))}
              </div>

              {reviewItems.length === 0 ? (
                <div className="rounded-[24px] border border-dashed border-slate-200 bg-slate-50 px-5 py-8 text-center text-sm text-slate-500">
                  当前结果尚未生成可展示的结构化审查要点，请改看 Markdown 报告。
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="rounded-[24px] border border-slate-200 bg-slate-50 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-medium text-slate-700">按审查大点 / 小点浏览</p>
                      <span className="text-xs text-slate-500">
                        {groupedReviewItems.length} 个大点 · {structuredStats.total} 个小点
                      </span>
                    </div>

                    <div className="mt-3 flex flex-wrap gap-3">
                      {groupedReviewItems.map((group, groupIndex) => (
                        <section key={`${group.section}-${groupIndex}`} className="rounded-[20px] border border-slate-200 bg-white p-3">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">
                                大点 {String(groupIndex + 1).padStart(2, "0")}
                              </p>
                              <h4 className="mt-2 text-sm font-semibold text-slate-900">{group.section}</h4>
                            </div>
                            <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-600">
                              {group.items.length} 项
                            </span>
                          </div>

                          <div className="mt-3 flex flex-wrap gap-2">
                            {group.items.map((item, itemIndex) => {
                              const active = selectedReviewItem && reviewItemKey(selectedReviewItem) === reviewItemKey(item);
                              const itemStatus = reviewItemStatusMeta(item.status);
                              const primaryRisk = getHighestRiskLevel(item.issues);

                              return (
                                <button
                                  key={reviewItemKey(item)}
                                  type="button"
                                  onClick={() => setSelectedReviewItemKey(reviewItemKey(item))}
                                  className={`rounded-[18px] border px-3 py-2 text-left transition ${
                                    active ? "border-brand-300 bg-brand-50 shadow-soft" : "border-slate-200 bg-slate-50 hover:border-brand-200 hover:bg-brand-50/50"
                                  }`}
                                >
                                  <div className="flex items-center gap-2">
                                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
                                      {groupIndex + 1}.{itemIndex + 1}
                                    </p>
                                    <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${itemStatus.tone}`}>
                                      {itemStatus.label}
                                    </span>
                                    {primaryRisk ? (
                                      <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${riskMeta(primaryRisk).badge}`}>
                                        {riskMeta(primaryRisk).label}
                                      </span>
                                    ) : null}
                                  </div>
                                  <p className="mt-1 line-clamp-1 text-sm font-semibold text-slate-900">{item.criterion}</p>
                                </button>
                              );
                            })}
                          </div>
                        </section>
                      ))}
                    </div>
                  </div>

                  {selectedReviewItem ? (
                    <article className="rounded-[24px] border border-brand-100 bg-white p-4 shadow-soft">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="eyebrow">Criterion Detail</p>
                          <h4 className="mt-2 text-lg font-semibold text-slate-900">{selectedReviewItem.criterion}</h4>
                          <p className="mt-2 text-sm text-slate-600">所属大点：{selectedReviewItem.section}</p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <span className={`rounded-full border px-3 py-1 text-xs font-medium ${reviewItemStatusMeta(selectedReviewItem.status).tone}`}>
                            {reviewItemStatusMeta(selectedReviewItem.status).label}
                          </span>
                          <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700">
                            {selectedReviewItem.issue_count} 条问题
                          </span>
                        </div>
                      </div>

                      {selectedReviewItem.status === "compliant" ? (
                        <div className="mt-4 rounded-[20px] border border-emerald-200 bg-emerald-50 px-4 py-4 text-sm leading-6 text-emerald-800">
                          该审查要点已通过，当前没有提取到需要处理的风险问题。
                        </div>
                      ) : selectedReviewItem.status === "error" ? (
                        <div className="mt-4 rounded-[20px] border border-rose-200 bg-rose-50 px-4 py-4 text-sm leading-6 text-rose-700">
                          该审查要点在执行过程中发生异常，建议查看 Markdown 报告或重新发起任务。
                        </div>
                      ) : selectedReviewItem.issues.length === 0 ? (
                        <div className="mt-4 rounded-[20px] border border-amber-200 bg-amber-50 px-4 py-4 text-sm leading-6 text-amber-800">
                          该审查要点已判定存在问题，但当前结构化解析未提取到细项，请结合 Markdown 报告查看完整结论。
                        </div>
                      ) : (
                        <div className="mt-4 space-y-4">
                          {selectedReviewItem.issues.map((issue, index) => {
                            const issueRisk = riskMeta(issue.risk_level);
                            const issueTitle =
                              issue.violated_criteria && issue.violated_criteria !== selectedReviewItem.criterion
                                ? issue.violated_criteria
                                : `问题 ${index + 1}`;

                            return (
                              <article key={`${reviewItemKey(selectedReviewItem)}-${index}`} className="rounded-[22px] border border-slate-200 bg-slate-50 p-4">
                                <div className="flex flex-wrap items-start justify-between gap-3">
                                  <div>
                                    <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">
                                      Issue {String(index + 1).padStart(2, "0")}
                                    </p>
                                    <h5 className="mt-2 text-base font-semibold text-slate-900">{issueTitle}</h5>
                                  </div>
                                  <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${issueRisk.badge}`}>{issueRisk.label}</span>
                                </div>

                                <div className="mt-4">
                                  <div className="rounded-[18px] border border-slate-200 bg-white px-4 py-3">
                                    <p className="text-xs font-semibold tracking-[0.18em] text-slate-500">条款位置</p>
                                    <p className="mt-2 text-sm leading-6 text-slate-700">{issue.clause_location || "未提供"}</p>
                                  </div>
                                </div>

                                <div className="mt-3 space-y-3">
                                  {[
                                    ["结论", issue.conclusion || "未提供"],
                                    ["分析", issue.analysis || "未提供"],
                                    ["修改建议", issue.suggestion || "未提供"],
                                    ["法律依据", issue.legal_basis || "未提供"],
                                  ].map(([label, value]) => (
                                    <div key={label} className="rounded-[18px] border border-slate-200 bg-white px-4 py-3">
                                      <p className="text-xs font-semibold tracking-[0.18em] text-slate-500">{label}</p>
                                      <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">{value}</p>
                                    </div>
                                  ))}
                                </div>
                              </article>
                            );
                          })}
                        </div>
                      )}
                    </article>
                  ) : null}
                </div>
              )}
            </div>
          ) : (
            <div className="mt-5 rounded-[24px] border border-dashed border-slate-200 bg-slate-50 px-5 py-8 text-center text-sm text-slate-500">
              审查完成后，这里会按大点和小点显示结构化结论，而不是只平铺问题卡片。
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
