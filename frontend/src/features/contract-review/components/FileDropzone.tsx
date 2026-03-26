import { ChangeEvent, DragEvent, useRef, useState } from "react";
import { FileText, UploadCloud } from "lucide-react";

interface FileDropzoneProps {
  step?: string;
  title: string;
  description: string;
  accept: string;
  file: File | null;
  accent: string;
  onFileSelect: (file: File) => void;
  onFileReject?: (message: string) => void;
}

function getFileExtension(filename: string) {
  const lastDotIndex = filename.lastIndexOf(".");
  return lastDotIndex === -1 ? "" : filename.slice(lastDotIndex).toLowerCase();
}

export function FileDropzone({
  step,
  title,
  description,
  accept,
  file,
  accent,
  onFileSelect,
  onFileReject,
}: FileDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const allowedExtensions = accept
    .split(",")
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean);

  const selectFile = (nextFile: File) => {
    const extension = getFileExtension(nextFile.name);
    if (!allowedExtensions.includes(extension)) {
      onFileReject?.(`仅支持 ${allowedExtensions.join(" / ")} 文件。`);
      return;
    }

    onFileSelect(nextFile);
  };

  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const nextFile = event.target.files?.[0];
    if (nextFile) {
      selectFile(nextFile);
    }
    event.target.value = "";
  };

  const handleDrop = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault();
    setIsDragging(false);
    const nextFile = event.dataTransfer.files?.[0];
    if (nextFile) {
      selectFile(nextFile);
    }
  };

  return (
    <div className="surface-panel rounded-[28px] p-5 text-slate-900">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          {step ? <p className="eyebrow">Step {step}</p> : null}
          <h2 className="mt-2 text-lg font-semibold text-slate-950">{title}</h2>
          <p className="mt-2 max-w-sm text-sm leading-6 text-slate-600">{description}</p>
        </div>
        <div
          className={`flex h-11 w-11 items-center justify-center rounded-2xl border border-slate-200 bg-gradient-to-br ${accent} shadow-soft`}
        >
          <FileText className="h-5 w-5 text-white" />
        </div>
      </div>

      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        className={`w-full rounded-[24px] border border-dashed px-5 py-7 text-left transition ${
          isDragging
            ? "border-brand-400 bg-brand-50"
            : "border-slate-300 bg-slate-50/80 hover:border-brand-400 hover:bg-brand-50/60"
        }`}
      >
        <div className="flex items-center gap-4">
          <div
            className={`flex h-12 w-12 items-center justify-center rounded-2xl transition ${
              isDragging ? "bg-brand-700 text-white shadow-soft" : "bg-white text-brand-700 shadow-soft"
            }`}
          >
            <UploadCloud className="h-6 w-6" />
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-slate-900">
              {file ? file.name : "点击选择文件，或将文件拖到这里"}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              {file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : `支持 ${accept.split(",").join(" / ")}`}
            </p>
          </div>
        </div>
      </button>

      <input ref={inputRef} type="file" accept={accept} className="hidden" onChange={handleChange} />
    </div>
  );
}
