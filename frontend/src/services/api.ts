export const API_BASE_URL = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

export type ReviewStatus = "pending" | "processing" | "completed" | "failed";
export type ReviewStage =
  | "queued"
  | "ingesting"
  | "building_tree"
  | "planning"
  | "reviewing"
  | "summarizing"
  | "generating_report"
  | "completed"
  | "failed";

export type ArtifactType = "md" | "docx" | "pdf";

export interface UploadResponse {
  file_path: string;
  original_filename: string;
  file_size?: number;
}

export interface Issue {
  clause_location: string;
  page?: number | null;
  risk_level: "high" | "medium" | "low" | "none";
  violated_criteria: string;
  conclusion: string;
  analysis: string;
  legal_basis?: string | null;
  suggestion: string;
}

export interface ReviewTaskResponse {
  task_id: string;
  status: ReviewStatus;
  created_at: string;
  contract_name?: string | null;
  stage?: ReviewStage | null;
  progress_message?: string | null;
  error?: string | null;
}

export interface ReviewResultResponse extends ReviewTaskResponse {
  contract_name: string;
  total_issues: number;
  issues: Issue[];
  report_md?: string | null;
  report_docx?: string | null;
  report_pdf?: string | null;
  completed_at?: string | null;
}

export interface HistoryItem {
  task_id: string;
  contract_name: string;
  status: ReviewStatus;
  created_at: string;
  completed_at?: string | null;
  stage?: ReviewStage | null;
  progress_message?: string | null;
  total_issues: number;
  error?: string | null;
}

interface ApiEnvelope<T> {
  success: boolean;
  message: string;
  data: T;
}

function toApiUrl(path: string) {
  return `${API_BASE_URL}${path}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(toApiUrl(path), init);

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      message = payload.detail || payload.message || message;
    } catch {
      // Keep the fallback message if the body is not JSON.
    }
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

export async function uploadContractFile(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const payload = await request<ApiEnvelope<UploadResponse>>("/api/v1/upload/contract", {
    method: "POST",
    body: formData,
  });

  return payload.data;
}

export async function uploadCriteriaFile(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const payload = await request<ApiEnvelope<UploadResponse>>("/api/v1/upload/criteria", {
    method: "POST",
    body: formData,
  });

  return payload.data;
}

export async function startReview(contractPath: string, criteriaPath: string): Promise<ReviewTaskResponse> {
  return request<ReviewTaskResponse>("/api/v1/review/start", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      contract_path: contractPath,
      criteria_path: criteriaPath,
    }),
  });
}

export async function getReviewStatus(taskId: string): Promise<ReviewTaskResponse> {
  return request<ReviewTaskResponse>(`/api/v1/review/${taskId}`);
}

export async function getReviewResult(taskId: string): Promise<ReviewResultResponse> {
  return request<ReviewResultResponse>(`/api/v1/review/${taskId}/result`);
}

export async function listReviewHistory(): Promise<HistoryItem[]> {
  return request<HistoryItem[]>("/api/v1/history");
}

export async function getHistoryItem(taskId: string): Promise<HistoryItem> {
  return request<HistoryItem>(`/api/v1/history/${taskId}`);
}

export function getReviewArtifactUrl(taskId: string, artifactType: ArtifactType) {
  return toApiUrl(`/api/v1/review/${taskId}/artifact/${artifactType}`);
}

export async function getReviewArtifactText(taskId: string, artifactType: ArtifactType): Promise<string> {
  const response = await fetch(getReviewArtifactUrl(taskId, artifactType));

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      message = payload.detail || payload.message || message;
    } catch {
      // Keep the fallback message if the body is not JSON.
    }
    throw new Error(message);
  }

  return response.text();
}
