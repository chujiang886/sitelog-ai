"use client";

import { apiFetch } from "@/lib/api";
import type {
  AnalyzeResponse,
  ImageMetadataResponse,
  UploadResponse,
} from "@/types/vision";

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024; // 与后端保持一致；pending_verification

export const ALLOWED_UPLOAD_MIME_TYPES: ReadonlyArray<string> = [
  "image/jpeg",
  "image/jpg",
  "image/png",
  "image/webp",
];

export class UploadValidationError extends Error {
  readonly code: string;
  constructor(code: string, message: string) {
    super(message);
    this.name = "UploadValidationError";
    this.code = code;
  }
}

export function validateFile(file: File): void {
  if (!(file instanceof File)) {
    throw new UploadValidationError("INVALID_FILE", "请选择文件后再上传");
  }
  if (!ALLOWED_UPLOAD_MIME_TYPES.includes(file.type)) {
    throw new UploadValidationError(
      "UNSUPPORTED_MIME",
      `不支持的文件类型：${file.type || "未知"}（仅 jpg/jpeg/png/webp）`,
    );
  }
  if (file.size <= 0) {
    throw new UploadValidationError("EMPTY_FILE", "文件为空");
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    throw new UploadValidationError(
      "FILE_TOO_LARGE",
      `文件超过 ${MAX_UPLOAD_BYTES / 1024 / 1024} MB`,
    );
  }
}

export interface UploadParams {
  file: File;
  projectId?: string;
  tenantId: string;
}

export async function uploadImage(params: UploadParams): Promise<UploadResponseData> {
  const { file, projectId, tenantId } = params;
  validateFile(file);

  const form = new FormData();
  form.append("file", file);
  if (projectId) {
    form.append("project_id", projectId);
  }

  const data = await apiFetch<UploadResponse["data"]>("/api/uploads", {
    method: "POST",
    body: form,
    headers: {
      "X-Tenant-Id": tenantId,
    },
  });
  return data;
}

export interface AnalyzeParams {
  imageId: string;
  tenantId: string;
}

export async function analyzeImage(
  params: AnalyzeParams,
): Promise<AnalyzeResponse["data"]> {
  const { imageId, tenantId } = params;
  const data = await apiFetch<AnalyzeResponse["data"]>("/api/vision/analyze", {
    method: "POST",
    headers: {
      "X-Tenant-Id": tenantId,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ image_id: imageId }),
  });
  return data;
}

export async function getImageMetadata(
  imageId: string,
  tenantId: string,
): Promise<ImageMetadataResponse["data"]> {
  return apiFetch<ImageMetadataResponse["data"]>(`/api/uploads/${imageId}`, {
    method: "GET",
    headers: {
      "X-Tenant-Id": tenantId,
    },
  });
}

// Re-export UploadResponseData type for callers that want the local alias.
export type UploadResponseData = UploadResponse["data"];