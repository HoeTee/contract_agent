import { useEffect, useState } from "react";
import { Clock3, RefreshCw, X } from "lucide-react";

import { HistoryItem, listReviewHistory } from "../../../services/api";

interface HistoryDrawerProps {
  open: boolean;
  activeTaskId: string | null;
  onClose: () => void;
  onSelectTask: (taskId: string) => void;
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function HistoryDrawer({ open, activeTaskId, onClose, onSelectTask }: HistoryDrawerProps) {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    listReviewHistory()
      .then((history) => {
        if (!cancelled) {
          setItems(history);
        }
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : "加载历史任务失败");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [open]);

  if (!open) {
    return null;
  }

  return (
    <>
      <div className="fixed inset-0 z-40 bg-slate-950/35 backdrop-blur-sm" onClick={onClose} />
      <aside className="fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col border-l border-slate-200 bg-slate-50/95 p-6 text-slate-900 shadow-panel backdrop-blur">
        <div className="flex items-center justify-between">
          <div>
            <p className="eyebrow">History</p>
            <h2 className="mt-2 font-serif text-2xl font-semibold text-slate-950">审查任务</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭历史记录"
            className="flex h-11 w-11 items-center justify-center rounded-full border border-slate-300 bg-white text-slate-600 transition hover:border-brand-300 hover:bg-brand-50 hover:text-brand-900"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-6 flex-1 space-y-3 overflow-y-auto">
          {isLoading ? (
            <div className="surface-subtle flex items-center gap-3 p-4 text-sm text-slate-600" role="status" aria-live="polite">
              <RefreshCw className="h-4 w-4 animate-spin" />
              正在加载历史任务...
            </div>
          ) : error ? (
            <div className="rounded-[24px] border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700" role="alert">
              {error}
            </div>
          ) : items.length === 0 ? (
            <div className="surface-subtle p-5 text-sm text-slate-500">目前还没有历史审查任务。</div>
          ) : (
            items.map((item) => (
              <button
                key={item.task_id}
                type="button"
                onClick={() => onSelectTask(item.task_id)}
                className={`w-full rounded-[24px] border p-4 text-left transition ${
                  item.task_id === activeTaskId
                    ? "border-brand-300 bg-brand-50 shadow-soft"
                    : "border-slate-200 bg-white hover:border-brand-200 hover:bg-brand-50/60"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium text-slate-900">{item.contract_name}</p>
                    <p className="mt-2 text-xs text-slate-500">{item.task_id}</p>
                  </div>
                  <div className="rounded-full border border-slate-200 bg-slate-100 px-3 py-1 text-xs text-slate-700">
                    {item.status}
                  </div>
                </div>

                <div className="mt-4 flex items-center gap-2 text-xs text-slate-500">
                  <Clock3 className="h-3.5 w-3.5" />
                  {formatTime(item.created_at)}
                </div>

                <div className="mt-3 flex items-center justify-between text-xs">
                  <span className="text-slate-600">{item.progress_message || item.stage || "Task created"}</span>
                  <span className="font-medium text-brand-800">{item.total_issues} 项</span>
                </div>
              </button>
            ))
          )}
        </div>
      </aside>
    </>
  );
}
