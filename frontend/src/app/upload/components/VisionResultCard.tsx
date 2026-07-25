"use client";

import type { JSX } from "react";

import type { VisionResult } from "@/types/vision";

interface VisionResultCardProps {
  status: "Pending" | "Processing" | "Done" | "Failed";
  result: VisionResult;
  pendingVerification: boolean;
}

const STATUS_BADGE: Record<VisionResultCardProps["status"], string> = {
  Pending: "bg-slate-200 text-slate-700",
  Processing: "bg-amber-100 text-amber-800",
  Done: "bg-emerald-100 text-emerald-800",
  Failed: "bg-rose-100 text-rose-800",
};

function asStringArray(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.filter((item): item is string => typeof item === "string");
  }
  return [];
}

export default function VisionResultCard({
  status,
  result,
  pendingVerification,
}: VisionResultCardProps): JSX.Element {
  const sceneType: string = result.scene_type ?? "unknown";
  const orientation: string = result.orientation_hint ?? "不确定";
  const quality: string = result.quality ?? "low";
  const obstructions: string[] = asStringArray(result.obstructions);
  const recommendations: string[] = asStringArray(result.recommendations);

  return (
    <div
      data-testid="vision-result"
      className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
    >
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-800">Vision 分析结果</h3>
        <span
          data-testid="vision-status-badge"
          className={`rounded-full px-3 py-1 text-xs font-medium ${STATUS_BADGE[status]}`}
        >
          {status}
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-xs text-slate-500">场景</dt>
          <dd className="mt-0.5 font-medium text-slate-800">{sceneType}</dd>
        </div>
        <div>
          <dt className="text-xs text-slate-500">朝向</dt>
          <dd className="mt-0.5 font-medium text-slate-800">{orientation}</dd>
        </div>
        <div>
          <dt className="text-xs text-slate-500">清晰度</dt>
          <dd className="mt-0.5 font-medium text-slate-800">{quality}</dd>
        </div>
        <div>
          <dt className="text-xs text-slate-500">provider</dt>
          <dd className="mt-0.5 font-mono text-xs text-slate-600">
            {result.provider ?? "pending_verification"}
          </dd>
        </div>
      </dl>

      <div>
        <p className="text-xs text-slate-500">障碍物</p>
        {obstructions.length === 0 ? (
          <p className="mt-1 text-sm text-slate-400">无</p>
        ) : (
          <ul className="mt-1 list-inside list-disc text-sm text-slate-700">
            {obstructions.map((item, idx) => (
              <li key={`obstruction-${idx}`}>{item}</li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <p className="text-xs text-slate-500">视觉建议</p>
        {recommendations.length === 0 ? (
          <p className="mt-1 text-sm text-slate-400">无</p>
        ) : (
          <ul className="mt-1 list-inside list-disc text-sm text-slate-700">
            {recommendations.map((item, idx) => (
              <li key={`rec-${idx}`}>{item}</li>
            ))}
          </ul>
        )}
      </div>

      {pendingVerification ? (
        <p
          data-testid="vision-pending"
          className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800"
        >
          当前结果携带 <span className="font-mono">pending_verification</span> 标记；待真实视觉模型接入后会自动取消。
        </p>
      ) : (
        <p
          data-testid="vision-verified"
          className="rounded-md bg-emerald-50 px-3 py-2 text-xs text-emerald-800"
        >
          已由 Vision Agent 真实分析（{result.provider ?? "未知 provider"}）。
        </p>
      )}
    </div>
  );
}