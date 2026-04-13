import { FileImage, FileText, ScanSearch } from "lucide-react";

interface DocumentPreviewProps {
  file: File | null;
  previewUrl: string | null;
  taskName?: string | null;
}

function renderFileBadge(file: File | null) {
  if (!file) {
    return null;
  }

  const extension = file.name.split(".").pop()?.toUpperCase() || "FILE";
  return (
    <span className="inline-flex items-center rounded-full border border-brand-100 bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700">
      {extension}
    </span>
  );
}

export function DocumentPreview({ file, previewUrl, taskName }: DocumentPreviewProps) {
  if (!file && !taskName) {
    return (
      <section className="surface-panel flex min-h-[420px] items-center justify-center p-10">
        <div className="max-w-md text-center">
          <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-[28px] bg-gradient-to-br from-brand-900 to-brand-600 text-white shadow-soft">
            <ScanSearch className="h-9 w-9" />
          </div>
          <h2 className="mt-6 font-serif text-3xl font-semibold text-slate-950">合同预览区</h2>
          <p className="mt-3 text-sm leading-7 text-slate-600">
            先上传合同和审查标准。这里用于快速核对原文；工作台负责控制任务，审查结论会在下方独立展示。
          </p>
        </div>
      </section>
    );
  }

  const isPdf = file?.type === "application/pdf" || file?.name.toLowerCase().endsWith(".pdf");
  const isImage = Boolean(file?.type.startsWith("image/"));

  return (
    <section className="surface-panel p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="eyebrow">Document Preview</p>
          <h2 className="mt-2 text-xl font-semibold text-slate-900">{file?.name || taskName}</h2>
        </div>
        {renderFileBadge(file)}
      </div>

      <div className="min-h-[420px] overflow-hidden rounded-[28px] border border-slate-200 bg-slate-50">
        {isPdf && previewUrl ? (
          <iframe title="合同预览" src={previewUrl} className="h-[420px] w-full border-0 bg-white" />
        ) : isImage && previewUrl ? (
          <img src={previewUrl} alt={file?.name || "合同预览"} className="h-[420px] w-full bg-white object-contain" />
        ) : (
          <div className="flex h-[420px] flex-col items-center justify-center px-8 text-center">
            <div className="flex h-20 w-20 items-center justify-center rounded-[28px] bg-brand-50 text-brand-700">
              {file?.type.startsWith("image/") ? <FileImage className="h-9 w-9" /> : <FileText className="h-9 w-9" />}
            </div>
            <p className="mt-6 text-lg font-medium text-slate-900">当前格式暂不支持直接预览</p>
            <p className="mt-3 max-w-md text-sm leading-7 text-slate-600">
              PDF 可以在浏览器内直接查看。DOCX 会先在服务端清洗、修订和批注，再进入审查流程，这比伪装为图片预览更可靠。
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
