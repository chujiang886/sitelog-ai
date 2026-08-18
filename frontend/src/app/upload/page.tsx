/**
 * Phase 1 / T08 — 图片上传 + Vision 分析页。
 *
 * 流程：
 *   1. 选择图片（拖拽 / 点击）；
 *   2. 本地预览；
 *   3. POST /api/uploads → 拿到 image_id；
 *   4. 自动 POST /api/vision/analyze 拉取 Vision 结果；
 *   5. 渲染 VisionResultCard。
 *
 * ## 身份来源（产品接通后的关键修正）
 * 早期版本用 localStorage 假造 tenantId，导致归属错乱。现在统一从登录会话
 * 取真实主体：``org_id`` 即租户 UUID，作为 ``X-Tenant-Id`` 传给上传与 Vision
 * 端点（二者都要求合法 UUID）。未登录时禁用提交并提示先登录。
 */

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ChangeEvent, JSX } from "react";

import ImageDropzone from "./components/ImageDropzone";
import VisionResultCard from "./components/VisionResultCard";
import {
  analyzeImage,
  UploadValidationError,
  uploadImage,
} from "@/lib/upload";
import {
  getIdentityProvider,
  IdentityUnauthenticatedError,
} from "@/lib/identity";
import type {
  UploadResponseData,
  VisionResult,
} from "@/types/vision";

type VisionStatus = "Pending" | "Processing" | "Done" | "Failed";

export default function UploadPage(): JSX.Element {
  const [tenantId, setTenantId] = useState<string>("");
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [uploadResponse, setUploadResponse] = useState<UploadResponseData | null>(
    null,
  );
  const [visionStatus, setVisionStatus] = useState<VisionStatus | null>(null);
  const [visionResult, setVisionResult] = useState<VisionResult>({});
  const [pendingVerification, setPendingVerification] = useState<boolean>(true);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // 取真实登录身份：org_id → tenantId（用于 X-Tenant-Id 头）。
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const me = await getIdentityProvider().getIdentity();
        if (cancelled) return;
        if (!me.orgId) {
          setError("登录身份缺少租户标识，请重新登录后再上传。");
          return;
        }
        setTenantId(me.orgId);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof IdentityUnauthenticatedError) {
          setError("请先登录后再上传图纸。");
          return;
        }
        setError("无法获取登录身份，请重新登录。");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const onFileInputChange = useCallback(
    (event: ChangeEvent<HTMLInputElement>) => {
      const next = event.target.files?.[0] ?? null;
      setFile(next);
      setUploadResponse(null);
      setVisionStatus(null);
      setVisionResult({});
      setPendingVerification(true);
      setError(null);
      event.target.value = "";
    },
    [],
  );

  const handleSelect = useCallback((selected: File) => {
    setFile(selected);
    setUploadResponse(null);
    setVisionStatus(null);
    setVisionResult({});
    setPendingVerification(true);
    setError(null);
  }, []);

  const handleSubmit = useCallback(async () => {
    if (!file) {
      setError("请先选择图片");
      return;
    }
    if (!tenantId) {
      setError("租户 ID 尚未就绪，请稍候");
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      const uploaded = await uploadImage({ file, tenantId });
      setUploadResponse(uploaded);
      setVisionStatus(uploaded.vision_status);
      setPendingVerification(uploaded.pending_verification);
      try {
        const analyzed = await analyzeImage({
          imageId: uploaded.image_id,
          tenantId,
        });
        setVisionStatus(analyzed.vision_status);
        setVisionResult(analyzed.vision_result);
        setPendingVerification(analyzed.pending_verification);
      } catch (analyzeErr) {
        // 上传成功但 analyze 失败 —— 不阻塞 UI，把异常显示给用户即可。
        const detail =
          analyzeErr instanceof Error ? analyzeErr.message : String(analyzeErr);
        setError(`Vision 分析失败：${detail}`);
      }
    } catch (err) {
      const detail =
        err instanceof UploadValidationError
          ? `${err.code}: ${err.message}`
          : err instanceof Error
            ? err.message
            : String(err);
      setError(detail);
    } finally {
      setIsSubmitting(false);
    }
  }, [file, tenantId]);

  const submitDisabled: boolean = useMemo(
    () => !file || isSubmitting || !tenantId,
    [file, isSubmitting, tenantId],
  );

  return (
    <section className="mx-auto flex max-w-3xl flex-col gap-4">
      <header>
        <p className="text-sm font-medium text-boip-primary-main">上传</p>
        <h1 className="mt-1 text-2xl font-semibold text-slate-900">
          上传阳台/窗户照片，让 Vision Agent 先看一步
        </h1>
      </header>

      <ImageDropzone onSelect={handleSelect} disabled={isSubmitting} />

      <div className="flex items-center gap-3">
        <label
          htmlFor="image-input-fallback"
          className="text-xs text-slate-500"
        >
          或选择文件：
        </label>
        <input
          id="image-input-fallback"
          data-testid="image-input-fallback"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          onChange={onFileInputChange}
          disabled={isSubmitting}
          className="text-xs"
        />
      </div>

      {previewUrl ? (
        <figure className="rounded-xl border border-slate-200 bg-white p-3">
          <img
            data-testid="image-preview"
            src={previewUrl}
            alt={file?.name ?? "preview"}
            className="max-h-72 w-full rounded-md object-contain"
          />
          <figcaption className="mt-2 text-xs text-slate-500">
            {file?.name} · {file ? Math.round(file.size / 1024) : 0} KB ·{" "}
            {file?.type}
          </figcaption>
        </figure>
      ) : null}

      <div className="flex items-center justify-between">
        <button
          type="button"
          data-testid="upload-submit"
          onClick={handleSubmit}
          disabled={submitDisabled}
          className="rounded-md bg-boip-primary-main px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {isSubmitting ? "上传中…" : "提交并触发 Vision"}
        </button>
        {uploadResponse ? (
          <span
            data-testid="upload-meta"
            className="text-xs text-slate-500"
          >
            image_id={uploadResponse.image_id.slice(0, 8)}… · sha256=
            {uploadResponse.sha256.slice(0, 12)}…
          </span>
        ) : null}
      </div>

      {error ? (
        <p
          role="alert"
          data-testid="upload-error"
          className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700"
        >
          {error}
        </p>
      ) : null}

      {visionStatus ? (
        <VisionResultCard
          status={visionStatus}
          result={visionResult}
          pendingVerification={pendingVerification}
        />
      ) : null}
    </section>
  );
}
