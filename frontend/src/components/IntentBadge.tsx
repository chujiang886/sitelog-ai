/**
 * Phase 1 / T06c — IntentBadge.
 *
 * Pure presentational component: maps NLU intent strings to Tailwind tokens.
 * Kept dependency-free (no chat.ts / no fetch) so it stays unit-testable in
 * isolation.
 */

import type { JSX } from "react";

export type IntentValue =
  | "consult"
  | "create_project"
  | "query_status"
  | "explain_plan"
  | "review_trigger"
  | "unknown"
  | string;

export interface IntentBadgeProps {
  intent: IntentValue | undefined | null;
  confidence?: number;
  method?: string;
  pendingVerification?: boolean;
}

interface IntentVisual {
  label: string;
  classes: string;
}

const INTENT_VISUALS: Record<string, IntentVisual> = {
  consult: {
    label: "通用咨询",
    classes: "bg-slate-100 text-slate-700 ring-slate-200",
  },
  create_project: {
    label: "创建项目",
    classes: "bg-blue-100 text-blue-800 ring-blue-200",
  },
  query_status: {
    label: "查询状态",
    classes: "bg-emerald-100 text-emerald-800 ring-emerald-200",
  },
  explain_plan: {
    label: "解释方案",
    classes: "bg-amber-100 text-amber-800 ring-amber-200",
  },
  review_trigger: {
    label: "人工复核",
    classes: "bg-rose-100 text-rose-800 ring-rose-200",
  },
  unknown: {
    label: "未识别",
    classes: "bg-slate-50 text-slate-500 ring-slate-200",
  },
};

function resolveVisual(intent: IntentValue | undefined | null): IntentVisual {
  if (!intent) {
    return INTENT_VISUALS.unknown;
  }
  return INTENT_VISUALS[intent] ?? {
    label: intent,
    classes: "bg-slate-100 text-slate-700 ring-slate-200",
  };
}

export default function IntentBadge(props: IntentBadgeProps): JSX.Element {
  const visual: IntentVisual = resolveVisual(props.intent);
  const confidencePct: string | null =
    typeof props.confidence === "number"
      ? `${Math.round(props.confidence * 100)}%`
      : null;
  const methodLabel: string | null =
    typeof props.method === "string" && props.method.length > 0
      ? props.method
      : null;

  return (
    <span
      data-testid="intent-badge"
      data-intent={props.intent ?? "unknown"}
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${visual.classes}`}
    >
      <span>{visual.label}</span>
      {confidencePct ? <span className="opacity-70">· {confidencePct}</span> : null}
      {methodLabel ? <span className="opacity-60">· {methodLabel}</span> : null}
      {props.pendingVerification ? (
        <span className="ml-1 rounded bg-amber-200 px-1 text-[10px] uppercase tracking-wide text-amber-900">
          pending
        </span>
      ) : null}
    </span>
  );
}