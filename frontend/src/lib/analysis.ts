/**
 * Phase 2 / T13 — 分析（三 Agent）+ 报告 API client。
 *
 * 与现有 chat.ts / upload.ts 风格保持一致：语义化函数封装 fetch，组件层
 * 不直接触碰裸 HTTP。
 *
 * 两条真实后端端点（契约已与主理人确认）：
 *   - POST /api/analysis/run       → 返回三段分析 dict + pending_verification + gaps
 *   - POST /api/report/generate    → 返回 application/pdf 字节流（Blob）
 *
 * 注意：这两个端点不走 BOIP 统一信封 {success, data}，而是返回裸 JSON / Blob，
 * 因此这里使用原生 fetch（而非 api.ts 的 apiFetch），并自行做 base URL 拼接与
 * 错误封装。base URL 与 api.ts 保持一致（NEXT_PUBLIC_API_BASE_URL，缺省 8000）。
 */

const API_BASE_URL: string =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const ANALYSIS_RUN_PATH = "/api/analysis/run";
const REPORT_GENERATE_PATH = "/api/report/generate";

/** sessionStorage 持久化键（consult → result 页面间传递分析结果）。 */
export const ANALYSIS_RESULT_STORAGE_KEY = "boip.analysis.result";
export const ANALYSIS_ADDRESS_STORAGE_KEY = "boip.analysis.address";

/**
 * 分析链路统一错误类型。与 ApiRequestError 区分命名，避免与 chat 信封错误混淆。
 */
export class AnalysisError extends Error {
  readonly code: string;
  readonly status?: number;

  constructor(code: string, message: string, status?: number) {
    super(message);
    this.name = "AnalysisError";
    this.code = code;
    this.status = status;
  }
}

/* ------------------------------------------------------------------ */
/* 契约类型定义                                                        */
/* ------------------------------------------------------------------ */

/** 经纬度坐标（可选）。 */
export interface Coordinates {
  lat: number;
  lng: number;
}

/**
 * 结构化咨询需求。 consult 页收集后传给 /api/analysis/run。
 * 字段均可选，便于前端逐步增强；后端缺失时按占位处理。
 */
export interface ConsultationInput {
  /** 开口偏好，例如「大落地窗」「通风为主」。 */
  opening_preference?: string;
  /** 预算档位，例如「经济」「中高端」。 */
  budget_tier?: string;
  /** 风格偏好，例如「现代极简」「新中式」。 */
  style_preference?: string;
  [key: string]: unknown;
}

/** /api/analysis/run 请求体（字段均可选/兼容）。 */
export interface AnalysisRequest {
  image_id?: string;
  address?: string;
  coordinates?: Coordinates;
  consultation?: ConsultationInput;
  vision_result?: Record<string, unknown>;
  region_hint?: string;
  [key: string]: unknown;
}

/** 视觉分析段落（即使 pending 也是 dict，含 pending_verification）。 */
export interface VisionAnalysis {
  scene_type?: string;
  orientation_hint?: string;
  obstructions?: string[];
  quality?: string;
  recommendations?: string[];
  pending_verification?: boolean;
  agent?: string;
  version?: string;
  [key: string]: unknown;
}

/** 环境分析段落。 */
export interface EnvironmentAnalysis {
  climate_zone?: string;
  prevailing_wind?: string;
  solar_exposure?: string;
  noise_level_hint?: string;
  regulatory_hints?: string[];
  regional_material_preference?: string;
  summary?: string;
  pending_verification?: boolean;
  [key: string]: unknown;
}

/** 设计方案候选条目。 */
export interface DesignCandidate {
  title?: string;
  opening_type?: string;
  frame_material?: string;
  glass_type?: string;
  dimensions_hint?: string;
  estimated_cost_tier?: string;
  pros?: string[];
  cons?: string[];
  rationale?: string;
}

/** 设计方案段落。 */
export interface DesignAnalysis {
  candidates?: DesignCandidate[];
  summary?: string;
  pending_verification?: boolean;
  [key: string]: unknown;
}

/** /api/analysis/run 响应（裸 JSON，无 BOIP 信封）。 */
export interface AnalysisResult {
  vision: VisionAnalysis;
  environment: EnvironmentAnalysis;
  design: DesignAnalysis;
  pending_verification: boolean;
  gaps: string[];
}

/** 生成报告时的项目上下文。 */
export interface ReportProject {
  address?: string;
  region_hint?: string;
  [key: string]: unknown;
}

/** /api/report/generate 请求体。 */
export interface ReportRequest {
  project?: ReportProject;
  vision?: VisionAnalysis | null;
  environment?: EnvironmentAnalysis | null;
  design?: DesignAnalysis | null;
}

/* ------------------------------------------------------------------ */
/* 内部工具                                                            */
/* ------------------------------------------------------------------ */

function buildJsonBody(payload: object): string {
  const record = payload as Record<string, unknown>;
  const cleaned: Record<string, unknown> = {};
  Object.keys(record).forEach((key) => {
    const value = record[key];
    // JSON.stringify 会忽略 undefined，但这里显式剔除，保证请求体语义清晰。
    if (value !== undefined) cleaned[key] = value;
  });
  return JSON.stringify(cleaned);
}

async function postJson(path: string, body: string): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
  } catch (err) {
    throw new AnalysisError(
      "NETWORK_ERROR",
      err instanceof Error ? err.message : String(err),
    );
  }
  if (!response.ok) {
    throw new AnalysisError(
      `HTTP_${response.status}`,
      `请求 ${path} 失败（HTTP ${response.status}）`,
      response.status,
    );
  }
  return response;
}

/* ------------------------------------------------------------------ */
/* 公开 API                                                            */
/* ------------------------------------------------------------------ */

/**
 * 触发三 Agent 分析（视觉 / 环境 / 设计）。
 *
 * @param payload 可选的需求上下文（地址、坐标、咨询结构化需求、视觉结果、区域提示）。
 * @returns 三段分析结果 + pending_verification + 信息缺口 gaps。
 * @throws AnalysisError 网络异常或 HTTP 非 2xx 时抛出。
 */
export async function runAnalysis(payload: AnalysisRequest): Promise<AnalysisResult> {
  const response = await postJson(ANALYSIS_RUN_PATH, buildJsonBody(payload));

  let data: AnalysisResult;
  try {
    data = (await response.json()) as AnalysisResult;
  } catch (err) {
    throw new AnalysisError(
      "INVALID_RESPONSE",
      err instanceof Error ? err.message : "分析接口返回了非 JSON 内容",
      response.status,
    );
  }

  // 防御性兜底：保证三段与 gaps 始终为可消费结构，UI 不会因缺字段而崩。
  return {
    vision: data.vision ?? {},
    environment: data.environment ?? {},
    design: data.design ?? {},
    pending_verification: Boolean(data.pending_verification),
    gaps: Array.isArray(data.gaps) ? data.gaps : [],
  };
}

/**
 * 生成 PDF 方案报告，返回 PDF Blob（不触发下载）。
 *
 * @param dossier 项目上下文 + 三段分析结果。
 * @returns application/pdf Blob。
 * @throws AnalysisError 网络异常或 HTTP 非 2xx 时抛出。
 */
export async function generateReport(dossier: ReportRequest): Promise<Blob> {
  const response = await postJson(REPORT_GENERATE_PATH, buildJsonBody(dossier));
  return response.blob();
}

/**
 * 生成报告并触发浏览器下载。
 *
 * jsdom 等无 URL.createObjectURL 的环境会安全跳过（不抛错），因此该辅助在单测中
 * 即使被误调用也不会让测试崩。真实浏览器中创建 object URL → <a download> 触发 →
 * 立即 revoke，避免内存泄漏。
 *
 * @param dossier 项目上下文 + 三段分析结果。
 * @param filename 下载文件名，缺省 boip_proposal.pdf。
 */
export async function downloadReport(
  dossier: ReportRequest,
  filename: string = "boip_proposal.pdf",
): Promise<void> {
  const blob = await generateReport(dossier);
  if (
    typeof window === "undefined" ||
    typeof URL === "undefined" ||
    typeof URL.createObjectURL !== "function"
  ) {
    return;
  }
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

/* ------------------------------------------------------------------ */
/* sessionStorage 持久化（consult → result 页面传递）                  */
/* ------------------------------------------------------------------ */

export function saveAnalysisResult(result: AnalysisResult): void {
  if (typeof window === "undefined" || typeof window.sessionStorage === "undefined") {
    return;
  }
  window.sessionStorage.setItem(ANALYSIS_RESULT_STORAGE_KEY, JSON.stringify(result));
}

export function loadAnalysisResult(): AnalysisResult | null {
  if (typeof window === "undefined" || typeof window.sessionStorage === "undefined") {
    return null;
  }
  const raw = window.sessionStorage.getItem(ANALYSIS_RESULT_STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AnalysisResult;
  } catch {
    return null;
  }
}

export function saveAnalysisAddress(address: string): void {
  if (typeof window === "undefined" || typeof window.sessionStorage === "undefined") {
    return;
  }
  window.sessionStorage.setItem(ANALYSIS_ADDRESS_STORAGE_KEY, address);
}

export function loadAnalysisAddress(): string {
  if (typeof window === "undefined" || typeof window.sessionStorage === "undefined") {
    return "";
  }
  return window.sessionStorage.getItem(ANALYSIS_ADDRESS_STORAGE_KEY) ?? "";
}

/** 清空本次会话传递的分析上下文（按需调用）。 */
export function clearAnalysisContext(): void {
  if (typeof window === "undefined" || typeof window.sessionStorage === "undefined") {
    return;
  }
  window.sessionStorage.removeItem(ANALYSIS_RESULT_STORAGE_KEY);
  window.sessionStorage.removeItem(ANALYSIS_ADDRESS_STORAGE_KEY);
}
