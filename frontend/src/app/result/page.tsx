/**
 * Phase 2 / T13 — 分析结果展示页。
 *
 * 从 sessionStorage 读取 consult 页写入的 AnalysisResult，分三段卡片展示：
 *   1. 视觉分析（scene_type / orientation_hint / obstructions / quality / recommendations）
 *   2. 环境分析（climate_zone / prevailing_wind / solar_exposure / noise / regulatory / material / summary）
 *   3. 设计方案（design.candidates[]，每个含标题 / 型材 / 玻璃 / 尺寸 / 成本 / 优劣 / 理由）
 *
 * 顶部显著展示 pending_verification 与 gaps；提供「下载 PDF 方案」按钮
 * （调用 generateReport → Blob → 浏览器下载）。
 *
 * 容错：某段缺失 / 为 null / 字段缺失时显示「暂无数据 / 待补充」，不崩。
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import type { JSX, ReactNode } from "react";

import {
  AnalysisError,
  downloadReport,
  loadAnalysisAddress,
  loadAnalysisResult,
  type AnalysisResult,
  type DesignCandidate,
  type EnvironmentAnalysis,
  type VisionAnalysis,
} from "@/lib/analysis";

/** 单段卡片容器。 */
function SectionCard({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}): JSX.Element {
  return (
    <section
      data-testid={`section-${title}`}
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <h2 className="mb-3 text-lg font-semibold text-slate-900">{title}</h2>
      <div className="space-y-2 text-sm text-slate-700">{children}</div>
    </section>
  );
}

/** 一个字段行（带标签 + 值，值缺失时优雅回退）。 */
function Field({ label, value }: { label: string; value?: string }): JSX.Element {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:gap-2">
      <span className="w-32 shrink-0 font-medium text-slate-500">{label}</span>
      <span className="text-slate-800">
        {value && value.trim().length > 0 ? value : "暂无数据 / 待补充"}
      </span>
    </div>
  );
}

/** 一个字符串列表字段（缺失 / 空时回退）。 */
function ListField({
  label,
  items,
}: {
  label: string;
  items?: string[];
}): JSX.Element {
  const hasItems = Array.isArray(items) && items.length > 0;
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:gap-2">
      <span className="w-32 shrink-0 font-medium text-slate-500">{label}</span>
      {hasItems ? (
        <ul className="list-disc space-y-0.5 pl-4 text-slate-800">
          {items.map((item, idx) => (
            <li key={`${label}-${idx}`}>{item}</li>
          ))}
        </ul>
      ) : (
        <span className="text-slate-800">暂无数据 / 待补充</span>
      )}
    </div>
  );
}

function VisionSection({ vision }: { vision: VisionAnalysis }): JSX.Element {
  return (
    <SectionCard title="视觉分析">
      <Field label="场景类型" value={vision.scene_type} />
      <Field label="朝向提示" value={vision.orientation_hint} />
      <Field label="图像质量" value={vision.quality} />
      <ListField label="遮挡物" items={vision.obstructions} />
      <ListField label="优化建议" items={vision.recommendations} />
    </SectionCard>
  );
}

function EnvironmentSection({
  environment,
}: {
  environment: EnvironmentAnalysis;
}): JSX.Element {
  return (
    <SectionCard title="环境分析">
      <Field label="气候分区" value={environment.climate_zone} />
      <Field label="主导风向" value={environment.prevailing_wind} />
      <Field label="日照条件" value={environment.solar_exposure} />
      <Field label="噪声提示" value={environment.noise_level_hint} />
      <Field
        label="区域用材偏好"
        value={environment.regional_material_preference}
      />
      <ListField label="规范提示" items={environment.regulatory_hints} />
      <Field label="小结" value={environment.summary} />
    </SectionCard>
  );
}

function CandidateCard({ candidate }: { candidate: DesignCandidate }): JSX.Element {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
      <h3 className="mb-2 text-base font-semibold text-slate-900">
        {candidate.title ?? "未命名方案"}
      </h3>
      <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
        <Field label="开口形式" value={candidate.opening_type} />
        <Field label="框体材质" value={candidate.frame_material} />
        <Field label="玻璃类型" value={candidate.glass_type} />
        <Field label="建议尺寸" value={candidate.dimensions_hint} />
        <Field label="预算档位" value={candidate.estimated_cost_tier} />
      </div>
      <ListField label="优势" items={candidate.pros} />
      <ListField label="劣势" items={candidate.cons} />
      <Field label="设计理由" value={candidate.rationale} />
    </div>
  );
}

function DesignSection({
  design,
}: {
  design: AnalysisResult["design"];
}): JSX.Element {
  const candidates = Array.isArray(design.candidates) ? design.candidates : [];
  return (
    <SectionCard title="设计方案">
      {candidates.length === 0 ? (
        <p className="text-sm text-slate-500">暂无候选方案 / 待补充</p>
      ) : (
        <div className="space-y-3">
          {candidates.map((candidate, idx) => (
            <CandidateCard key={`candidate-${idx}`} candidate={candidate} />
          ))}
        </div>
      )}
      {design.summary ? (
        <p className="mt-3 rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600">
          {design.summary}
        </p>
      ) : null}
    </SectionCard>
  );
}

export default function ResultPage(): JSX.Element {
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [address, setAddress] = useState<string>("");
  const [loaded, setLoaded] = useState<boolean>(false);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  useEffect(() => {
    const data = loadAnalysisResult();
    setResult(data);
    setAddress(loadAnalysisAddress());
    setLoaded(true);
  }, []);

  const handleDownload = useCallback(async () => {
    if (!result || isGenerating) return;
    setIsGenerating(true);
    setDownloadError(null);
    try {
      await downloadReport({
        project: address ? { address } : {},
        vision: result.vision ?? null,
        environment: result.environment ?? null,
        design: result.design ?? null,
      });
    } catch (err) {
      const detail =
        err instanceof AnalysisError
          ? `${err.code}: ${err.message}`
          : err instanceof Error
            ? err.message
            : String(err);
      setDownloadError(detail);
    } finally {
      setIsGenerating(false);
    }
  }, [result, address, isGenerating]);

  if (loaded && !result) {
    return (
      <section className="mx-auto flex max-w-3xl flex-col gap-4 py-10">
        <header>
          <p className="text-sm font-medium text-boip-primary-main">分析结果</p>
          <h1 className="mt-1 text-2xl font-semibold text-slate-900">
            暂无分析结果
          </h1>
        </header>
        <p className="rounded-md bg-slate-50 px-3 py-4 text-sm text-slate-500">
          请先在
          <a className="mx-1 text-boip-primary-main underline" href="/consult">
            咨询页
          </a>
          填写需求并点击「生成设计方案」。
        </p>
      </section>
    );
  }

  if (!result) {
    // 尚未从 sessionStorage 读取完成（SSR / 首帧）。
    return (
      <section className="mx-auto max-w-3xl py-10">
        <p className="text-sm text-slate-400">加载分析结果…</p>
      </section>
    );
  }

  const vision = result.vision ?? {};
  const environment = result.environment ?? {};
  const design = result.design ?? {};
  const gaps = Array.isArray(result.gaps) ? result.gaps : [];

  return (
    <section className="mx-auto flex max-w-4xl flex-col gap-4 py-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-boip-primary-main">分析结果</p>
          <h1 className="mt-1 text-2xl font-semibold text-slate-900">
            三 Agent 联合方案
          </h1>
          {address ? (
            <p className="mt-1 text-xs text-slate-400">项目地址：{address}</p>
          ) : null}
        </div>
        <button
          type="button"
          data-testid="result-download"
          onClick={handleDownload}
          disabled={isGenerating}
          className="rounded-md bg-boip-primary-main px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {isGenerating ? "生成中…" : "下载 PDF 方案"}
        </button>
      </header>

      {result.pending_verification ? (
        <div
          role="alert"
          data-testid="result-pending"
          className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800"
        >
          <strong className="font-semibold">AI 结果待人工核实。</strong>
          <span className="ml-1">
            当前为占位分析，正式 LLM 接入后将自动替换并更新核实状态。
          </span>
        </div>
      ) : null}

      {gaps.length > 0 ? (
        <div
          data-testid="result-gaps"
          className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600"
        >
          <p className="mb-1 font-medium text-slate-700">待补充信息（gaps）：</p>
          <ul className="list-disc space-y-0.5 pl-4">
            {gaps.map((gap, idx) => (
              <li key={`gap-${idx}`}>{gap}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {downloadError ? (
        <p
          role="alert"
          data-testid="result-download-error"
          className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700"
        >
          {downloadError}
        </p>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <VisionSection vision={vision} />
        <EnvironmentSection environment={environment} />
        <div className="lg:col-span-2">
          <DesignSection design={design} />
        </div>
      </div>
    </section>
  );
}
