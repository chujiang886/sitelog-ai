// T08｜上传 / Vision 客户端（Phase 1 / T08）
// 契约：所有接口统一返回 {success, data} / {success, data, error}
// 失败兜底：HTTP 4xx/5xx → ApiRequestError(code, message, status)
// 不杜撰行业数据；超时 / 体积阈值标 pending_verification
//
// 依赖：浏览器 fetch；AbortController（用于取消上传）

const API_BASE = process.env.NEXT_PUBLIC_BOIP_API_BASE ?? "/api";

export interface UploadResponse {
  image_id: string;
  sha256: string;
  vision_status: "Pending" | "Processing" | "Done" | "Failed";
  filename: string;
  size_bytes: number;
}

export interface ImageRecord {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  vision_status: "Pending" | "Processing" | "Done" | "Failed";
  vision_result: Record<string, unknown> | null;
  created_at: string;
}

export interface VisionAnalysisResponse {
  image_id: string;
  vision_result: Record<string, unknown>;
  pending_verification: boolean;
}

export class ApiRequestError extends Error {
  readonly code: string;
  readonly status: number;
  constructor(code: string, message: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

async function parseEnvelope<T>(resp: Response): Promise<T> {
  let payload: unknown;
  try {
    payload = await resp.json();
  } catch {
    throw new ApiRequestError(
      "INVALID_JSON",
      `服务端返回非 JSON (HTTP ${resp.status})`,
      resp.status,
    );
  }
  if (
    payload &&
    typeof payload === "object" &&
    "success" in payload &&
    (payload as { success: boolean }).success === true &&
    "data" in payload
  ) {
    return (payload as { data: T }).data;
  }
  const err =
    payload && typeof payload === "object" && "error" in payload
      ? (payload as { error: { code?: string; message?: string } }).error
      : null;
  throw new ApiRequestError(
    err?.code ?? "UNKNOWN_ERROR",
    err?.message ?? `请求失败 (HTTP ${resp.status})`,
    resp.status,
  );
}

function buildHeaders(extra?: Record<string, string>): Record<string, string> {
  // Phase 1 占位：X-Tenant-Id / X-User-Id 来自登录后的 session
  const tenant = process.env.NEXT_PUBLIC_BOIP_TENANT_ID ?? "tenant-1";
  const user = process.env.NEXT_PUBLIC_BOIP_USER_ID ?? "user-1";
  return {
    "X-Tenant-Id": tenant,
    "X-User-Id": user,
    ...extra,
  };
}

export async function uploadImage(
  file: File,
  projectId?: string,
  signal?: AbortSignal,
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  if (projectId) form.append("project_id", projectId);
  const resp = await fetch(`${API_BASE}/uploads`, {
    method: "POST",
    body: form,
    headers: buildHeaders(),
    signal,
  });
  return parseEnvelope<UploadResponse>(resp);
}

export async function getImage(imageId: string): Promise<ImageRecord> {
  const resp = await fetch(`${API_BASE}/uploads/${imageId}`, {
    method: "GET",
    headers: buildHeaders(),
  });
  return parseEnvelope<ImageRecord>(resp);
}

export async function analyzeImage(
  imageId: string,
): Promise<VisionAnalysisResponse> {
  const resp = await fetch(`${API_BASE}/vision/analyze`, {
    method: "POST",
    headers: buildHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ image_id: imageId }),
  });
  return parseEnvelope<VisionAnalysisResponse>(resp);
}