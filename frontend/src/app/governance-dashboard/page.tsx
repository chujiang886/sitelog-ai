"use client";

/**
 * Phase 3.8.26 企业智能体治理驾驶舱 —— 人工操作界面。
 *
 * 设计红线（与后端同源，fail-closed）：
 * - 本页面仅面向**真实责任人（USER）**；所有请求携带 x-actor-id / x-actor-kind=user。
 * - **无自动按钮**：任何确认动作必须人工点击 + 填写理由，AI 绝不代点。
 * - 本页面不持有任何治理状态，只读查询 + 提交人工确认；审批/执行/关闭均由后端编排器
 *   在强制 USER 下推进（后端再次拦截 AI 越权）。
 *
 * 说明：真实责任人身份由网关 / 鉴权层注入请求头；此处演示用责任人（human-only）。
 */

import { useCallback, useEffect, useState } from "react";

const API_BASE: string =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// 演示用责任人（human-only，actor_kind 必须为 user）。生产由鉴权注入。
const ACTOR_HEADERS: Record<string, string> = {
  "x-actor-id": "governor-1",
  "x-actor-kind": "user",
};

type GovStatus =
  | "created"
  | "under_review"
  | "human_confirmed"
  | "in_progress"
  | "waiting_result"
  | "completed";

interface WorkflowView {
  workflow_id: string;
  title: string;
  status: GovStatus;
  description?: string;
  source_facts: string[];
  references: string[];
  created_by?: string;
}

type Decision = "confirmed" | "rejected" | "need_more_info";

const STATUS_LABEL: Record<GovStatus, string> = {
  created: "候选",
  under_review: "待研判",
  human_confirmed: "已确认",
  in_progress: "执行中",
  waiting_result: "待确认结果",
  completed: "已完成",
};

export default function GovernanceDashboardPage(): JSX.Element {
  const [workflows, setWorkflows] = useState<WorkflowView[]>([]);
  const [pending, setPending] = useState<WorkflowView[]>([]);
  const [error, setError] = useState<string>("");
  const [busyId, setBusyId] = useState<string>("");
  const [reason, setReason] = useState<Record<string, string>>({});
  const [decision, setDecision] = useState<Record<string, Decision>>({});

  const load = useCallback(async (): Promise<void> => {
    setError("");
    try {
      const [wfRes, revRes] = await Promise.all([
        fetch(`${API_BASE}/governance/workflows`, { headers: ACTOR_HEADERS }),
        fetch(`${API_BASE}/governance/reviews`, { headers: ACTOR_HEADERS }),
      ]);
      if (!wfRes.ok) throw new Error(`加载工作流失败（${wfRes.status}）`);
      if (!revRes.ok) throw new Error(`加载待研判失败（${revRes.status}）`);
      setWorkflows((await wfRes.json()) as WorkflowView[]);
      setPending((await revRes.json()) as WorkflowView[]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const confirm = async (wid: string): Promise<void> => {
    setBusyId(wid);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/governance/review/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...ACTOR_HEADERS },
        body: JSON.stringify({
          workflow_id: wid,
          decision: decision[wid] ?? "confirmed",
          reason: reason[wid] ?? "",
        }),
      });
      if (!res.ok) {
        const detail = await res.text().catch(() => "");
        throw new Error(`确认失败（${res.status}）${detail ? `：${detail}` : ""}`);
      }
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "确认失败");
    } finally {
      setBusyId("");
    }
  };

  return (
    <section className="mx-auto max-w-5xl px-6 py-10">
      <p className="text-sm font-medium text-boip-primary-main">治理责任人专属</p>
      <h1 className="mt-2 text-3xl font-semibold text-slate-900">治理驾驶舱</h1>
      <p className="mt-2 text-sm text-slate-500">
        查看治理线索与事实摘要、研判确认、追踪执行。所有动作均须真实责任人操作，AI 不代点。
      </p>

      {error ? (
        <p className="mt-6 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      <h2 className="mt-8 text-xl font-semibold text-slate-800">
        待人工研判（{pending.length}）
      </h2>
      {pending.length === 0 ? (
        <p className="mt-3 text-sm text-slate-400">暂无待研判项。</p>
      ) : (
        <div className="mt-3 space-y-4">
          {pending.map((wf) => (
            <article
              key={wf.workflow_id}
              className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-slate-900">{wf.title}</h3>
                <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-700">
                  {STATUS_LABEL[wf.status]}
                </span>
              </div>
              <p className="mt-1 text-xs text-slate-400">#{wf.workflow_id}</p>

              <div className="mt-4">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
                  事实摘要
                </p>
                <ul className="mt-1 list-disc pl-5 text-sm text-slate-700">
                  {wf.source_facts.map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                </ul>
              </div>

              <div className="mt-3">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
                  来源
                </p>
                <ul className="mt-1 list-disc pl-5 text-sm text-slate-500">
                  {wf.references.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </div>

              <div className="mt-4 rounded-lg bg-slate-50 p-3">
                <label className="block text-xs font-medium text-slate-600">
                  研判决定
                  <select
                    className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
                    value={decision[wf.workflow_id] ?? "confirmed"}
                    onChange={(e) =>
                      setDecision((d) => ({
                        ...d,
                        [wf.workflow_id]: e.target.value as Decision,
                      }))
                    }
                  >
                    <option value="confirmed">确认（同意处置）</option>
                    <option value="rejected">驳回</option>
                    <option value="need_more_info">需补充信息</option>
                  </select>
                </label>
                <textarea
                  className="mt-2 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
                  rows={2}
                  placeholder="请填写研判理由（必填，留痕审计）"
                  value={reason[wf.workflow_id] ?? ""}
                  onChange={(e) =>
                    setReason((r) => ({
                      ...r,
                      [wf.workflow_id]: e.target.value,
                    }))
                  }
                />
                <button
                  type="button"
                  disabled={busyId === wf.workflow_id}
                  onClick={() => void confirm(wf.workflow_id)}
                  className="mt-2 rounded-md bg-boip-primary-main px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                >
                  {busyId === wf.workflow_id ? "提交中…" : "人工确认"}
                </button>
              </div>
            </article>
          ))}
        </div>
      )}

      <h2 className="mt-10 text-xl font-semibold text-slate-800">
        全部治理工作流（{workflows.length}）
      </h2>
      <div className="mt-3 space-y-2">
        {workflows.map((wf) => (
          <div
            key={wf.workflow_id}
            className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm"
          >
            <span className="font-medium text-slate-800">{wf.title}</span>
            <span className="rounded-full bg-slate-100 px-3 py-0.5 text-xs text-slate-600">
              {STATUS_LABEL[wf.status]}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
