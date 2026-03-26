import { AlertTriangle, FileSearch, Scale, ShieldAlert, ShieldCheck } from "lucide-react";

import { ReviewResultResponse } from "../../../services/api";

interface IssueSummaryProps {
  result: ReviewResultResponse | null;
}

function getRiskMeta(level: "high" | "medium" | "low" | "none") {
  switch (level) {
    case "high":
      return { label: "High", className: "border-rose-400/30 bg-rose-400/10 text-rose-100" };
    case "medium":
      return { label: "Medium", className: "border-amber-300/30 bg-amber-300/10 text-amber-100" };
    case "low":
      return { label: "Low", className: "border-cyan-300/30 bg-cyan-300/10 text-cyan-100" };
    default:
      return { label: "None", className: "border-emerald-300/30 bg-emerald-300/10 text-emerald-100" };
  }
}

export function IssueSummary({ result }: IssueSummaryProps) {
  if (!result) {
    return (
      <section className="rounded-[32px] border border-white/10 bg-slate-950/60 p-8 shadow-2xl shadow-slate-950/40">
        <div className="flex items-center gap-4">
          <div className="flex h-16 w-16 items-center justify-center rounded-[24px] bg-white/10 text-slate-100">
            <FileSearch className="h-8 w-8" />
          </div>
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.24em] text-slate-400">Results</p>
            <h2 className="mt-2 text-2xl font-semibold text-white">Waiting for a completed task</h2>
          </div>
        </div>
        <p className="mt-5 max-w-3xl text-sm leading-7 text-slate-300">
          Once the task completes, the issue list, risk summary, and report downloads will appear here.
        </p>
      </section>
    );
  }

  const counts = result.issues.reduce(
    (summary, issue) => {
      summary[issue.risk_level] += 1;
      return summary;
    },
    { high: 0, medium: 0, low: 0, none: 0 },
  );

  return (
    <section className="rounded-[32px] border border-white/10 bg-slate-950/60 p-8 shadow-2xl shadow-slate-950/40">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium uppercase tracking-[0.24em] text-slate-400">Results</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">{result.contract_name}</h2>
        </div>
        <div className="rounded-[24px] border border-emerald-300/20 bg-emerald-300/10 px-4 py-3 text-right">
          <p className="text-xs uppercase tracking-[0.22em] text-emerald-100/80">Total issues</p>
          <p className="mt-1 text-2xl font-semibold text-emerald-50">{result.total_issues}</p>
        </div>
      </div>

      <div className="mt-6 grid gap-4 md:grid-cols-4">
        {[
          { label: "High risk", value: counts.high, icon: ShieldAlert, tone: "from-rose-500/30 to-rose-400/5" },
          { label: "Medium risk", value: counts.medium, icon: AlertTriangle, tone: "from-amber-400/30 to-amber-300/5" },
          { label: "Low risk", value: counts.low, icon: Scale, tone: "from-cyan-400/30 to-cyan-300/5" },
          { label: "No risk", value: counts.none, icon: ShieldCheck, tone: "from-emerald-400/30 to-emerald-300/5" },
        ].map((card) => (
          <div
            key={card.label}
            className={`rounded-[24px] border border-white/10 bg-gradient-to-br ${card.tone} p-5`}
          >
            <div className="flex items-center justify-between">
              <p className="text-sm text-slate-200">{card.label}</p>
              <card.icon className="h-4 w-4 text-slate-100" />
            </div>
            <p className="mt-4 text-3xl font-semibold text-white">{card.value}</p>
          </div>
        ))}
      </div>

      <div className="mt-8 space-y-4">
        {result.issues.map((issue, index) => {
          const risk = getRiskMeta(issue.risk_level);
          return (
            <article key={`${issue.violated_criteria}-${index}`} className="rounded-[28px] border border-white/10 bg-black/20 p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h3 className="text-lg font-medium text-white">{issue.violated_criteria || `Issue ${index + 1}`}</h3>
                <span className={`rounded-full border px-3 py-1 text-xs font-medium ${risk.className}`}>
                  {risk.label}
                </span>
              </div>

              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <div className="rounded-[20px] border border-white/10 bg-white/[0.03] p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Location</p>
                  <p className="mt-2 text-sm leading-7 text-slate-100">{issue.clause_location || "Not provided"}</p>
                </div>
                <div className="rounded-[20px] border border-white/10 bg-white/[0.03] p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Conclusion</p>
                  <p className="mt-2 text-sm leading-7 text-slate-100">{issue.conclusion || "Not provided"}</p>
                </div>
              </div>

              <div className="mt-4 rounded-[20px] border border-white/10 bg-white/[0.03] p-4">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Analysis</p>
                <p className="mt-2 text-sm leading-7 text-slate-100">{issue.analysis || "Not provided"}</p>
              </div>

              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <div className="rounded-[20px] border border-white/10 bg-white/[0.03] p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Suggestion</p>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-slate-100">{issue.suggestion || "Not provided"}</p>
                </div>
                <div className="rounded-[20px] border border-white/10 bg-white/[0.03] p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Legal basis</p>
                  <p className="mt-2 text-sm leading-7 text-slate-100">{issue.legal_basis || "Not provided"}</p>
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
