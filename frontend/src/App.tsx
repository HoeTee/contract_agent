import { useEffect, useState } from "react";
import { Clock3, FolderClock, ShieldCheck } from "lucide-react";

import { DocumentPreview } from "./features/contract-review/components/DocumentPreview";
import { FileDropzone } from "./features/contract-review/components/FileDropzone";
import { HistoryDrawer } from "./features/contract-review/components/HistoryDrawer";
import { ReviewConclusionPanel } from "./features/contract-review/components/ReviewConclusionPanel";
import { TaskStatusPanel } from "./features/contract-review/components/TaskStatusPanel";
import {
  RetrievalMode,
  ReviewResultResponse,
  ReviewTaskResponse,
  getReviewSettings,
  getReviewResult,
  getReviewStatus,
  startReview,
  uploadContractFile,
  uploadCriteriaFile,
} from "./services/api";

function getErrorMessage(reason: unknown) {
  return reason instanceof Error ? reason.message : "发生未知错误";
}

export default function App() {
  const [contractFile, setContractFile] = useState<File | null>(null);
  const [criteriaFile, setCriteriaFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [task, setTask] = useState<ReviewTaskResponse | null>(null);
  const [result, setResult] = useState<ReviewResultResponse | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [defaultRetrievalMode, setDefaultRetrievalMode] = useState<RetrievalMode>("llamaindex");
  const [defaultWebSearchEnabled, setDefaultWebSearchEnabled] = useState(false);

  useEffect(() => {
    let cancelled = false;

    getReviewSettings()
      .then((settings) => {
        if (cancelled) return;
        setDefaultRetrievalMode(settings.default_retrieval_mode);
        setDefaultWebSearchEnabled(settings.default_web_search_enabled);
      })
      .catch(() => {
        // Keep local fallbacks when the backend settings are temporarily unavailable.
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!contractFile) {
      setPreviewUrl(null);
      return;
    }

    const nextPreviewUrl = URL.createObjectURL(contractFile);
    setPreviewUrl(nextPreviewUrl);

    return () => {
      URL.revokeObjectURL(nextPreviewUrl);
    };
  }, [contractFile]);

  useEffect(() => {
    if (!task || task.status !== "processing") {
      return;
    }

    const timer = window.setTimeout(async () => {
      try {
        const nextTask = await getReviewStatus(task.task_id);
        setTask(nextTask);

        if (nextTask.status === "completed") {
          const nextResult = await getReviewResult(nextTask.task_id);
          setResult(nextResult);
        }

        if (nextTask.status === "failed") {
          setError(nextTask.error || "审查失败");
        }
      } catch (reason) {
        setError(getErrorMessage(reason));
      }
    }, 2000);

    return () => {
      window.clearTimeout(timer);
    };
  }, [task]);

  const handleContractSelect = (file: File) => {
    setContractFile(file);
    setTask(null);
    setResult(null);
    setError(null);
  };

  const handleCriteriaSelect = (file: File) => {
    setCriteriaFile(file);
    setTask(null);
    setResult(null);
    setError(null);
  };

  const handleStartReview = async (retrievalMode: RetrievalMode, webSearchEnabled: boolean) => {
    if (!contractFile || !criteriaFile) {
      setError("请先上传合同文件和审查标准。");
      return;
    }

    setError(null);
    setResult(null);
    setTask(null);
    setIsStarting(true);

    try {
      const [contractUpload, criteriaUpload] = await Promise.all([
        uploadContractFile(contractFile),
        uploadCriteriaFile(criteriaFile),
      ]);

      const createdTask = await startReview(
        contractUpload.file_path,
        criteriaUpload.file_path,
        retrievalMode,
        webSearchEnabled,
      );
      setTask(createdTask);
    } catch (reason) {
      setError(getErrorMessage(reason));
    } finally {
      setIsStarting(false);
    }
  };

  const handleReset = () => {
    setContractFile(null);
    setCriteriaFile(null);
    setTask(null);
    setResult(null);
    setError(null);
  };

  const handleSelectHistoryTask = async (taskId: string) => {
    setHistoryOpen(false);
    setContractFile(null);
    setCriteriaFile(null);
    setResult(null);
    setError(null);

    try {
      const nextTask = await getReviewStatus(taskId);
      setTask(nextTask);

      if (nextTask.status === "completed") {
        const nextResult = await getReviewResult(taskId);
        setResult(nextResult);
      }

      if (nextTask.status === "failed") {
        setError(nextTask.error || "审查失败");
      }
    } catch (reason) {
      setError(getErrorMessage(reason));
    }
  };

  const activeTaskId = result?.task_id || task?.task_id || null;

  return (
    <div className="min-h-screen bg-legal-shell text-slate-900">
      <div className="mx-auto flex min-h-screen max-w-[1600px] flex-col px-5 py-8 sm:px-6 lg:px-8">
        <header className="surface-panel relative overflow-hidden px-6 py-7 sm:px-8">
          <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-brand-300 to-trust-300" />
          <div className="flex flex-wrap items-start justify-between gap-6">
            <div>
              <p className="eyebrow">Deep Research Agent</p>
              <h1 className="mt-4 max-w-3xl font-serif text-4xl font-semibold tracking-tight text-slate-950 sm:text-5xl">
                合同法律审查智能体
              </h1>
              <p className="mt-4 max-w-3xl text-sm leading-7 text-slate-600 sm:text-base">
                上传合同与审查标准，跟踪任务阶段，并在独立审查结论板块中查看结构化风险明细、Markdown 报告与历史任务。
              </p>
              <div className="mt-5 flex flex-wrap gap-2">
                <span className="badge-muted">结构化风险结论</span>
                <span className="badge-muted">长任务跟踪</span>
                <span className="badge-muted">Markdown / 批注合同 DOCX / PDF 导出</span>
              </div>
            </div>

            <div className="flex flex-wrap gap-3">
              <button type="button" onClick={() => setHistoryOpen(true)} className="action-secondary">
                <FolderClock className="h-4 w-4" />
                审查历史
              </button>
              <div className="inline-flex items-center gap-2 rounded-full border border-brand-100 bg-brand-50 px-5 py-3 text-sm font-medium text-brand-800">
                <ShieldCheck className="h-4 w-4" />
                法务工作流模式
              </div>
              <div className="inline-flex items-center gap-2 rounded-full border border-trust-100 bg-trust-50 px-5 py-3 text-sm font-medium text-trust-800">
                <Clock3 className="h-4 w-4" />
                品牌蓝绿工作台
              </div>
            </div>
          </div>
        </header>

        <main className="mt-6 flex-1 space-y-6">
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.08fr)_minmax(430px,0.92fr)] 2xl:grid-cols-[minmax(0,1.1fr)_minmax(520px,0.9fr)]">
            <div className="space-y-6">
              <div className="grid gap-4 lg:grid-cols-2">
                <FileDropzone
                  step="01"
                  title="合同文件"
                  description="上传 PDF 或 DOCX。PDF 可直接预览，DOCX 会先在服务端清洗和转换后再进入审查流程。"
                  accept=".pdf,.docx"
                  file={contractFile}
                  accent="from-brand-900 via-brand-700 to-brand-600"
                  onFileSelect={handleContractSelect}
                  onFileReject={setError}
                />
                <FileDropzone
                  step="02"
                  title="审查标准"
                  description="上传 PDF 或 DOCX 格式的审查标准文件，系统将据此生成结构化审查结论。"
                  accept=".pdf,.docx"
                  file={criteriaFile}
                  accent="from-trust-800 via-trust-600 to-trust-500"
                  onFileSelect={handleCriteriaSelect}
                  onFileReject={setError}
                />
              </div>

              <DocumentPreview file={contractFile} previewUrl={previewUrl} taskName={task?.contract_name} />
            </div>

            <TaskStatusPanel
              contractFile={contractFile}
              criteriaFile={criteriaFile}
              task={task}
              result={result}
              isStarting={isStarting}
              error={error}
              onStart={handleStartReview}
              onReset={handleReset}
              defaultRetrievalMode={defaultRetrievalMode}
              defaultWebSearchEnabled={defaultWebSearchEnabled}
            />
          </div>

          <ReviewConclusionPanel result={result} task={task} />
        </main>
      </div>

      <HistoryDrawer
        open={historyOpen}
        activeTaskId={activeTaskId}
        onClose={() => setHistoryOpen(false)}
        onSelectTask={handleSelectHistoryTask}
      />
    </div>
  );
}
