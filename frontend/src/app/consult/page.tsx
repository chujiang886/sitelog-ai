/**
 * Phase 2 / T13 — Consult page (NLU 咨询 + 三 Agent 分析入口).
 *
 * 在 T06c 已有的 NLU 聊天流程之上，新增「结构化需求」面板：
 *   1. 保留原有 NLU 提交（appendMessage → 助手占位回复 + 意图标签）。
 *   2. 新增地址 / 区域提示 / 开口偏好 / 预算档位 / 风格偏好等可选字段。
 *   3. 点击「生成设计方案」→ 调用 runAnalysis → 结果写入 sessionStorage →
 *      路由跳转至 /result 展示并支持 PDF 下载。
 *
 * 三 Agent 无 LLM key 时返回 pending 占位，UI 通过跳转后结果页的
 * pending_verification 横幅优雅展示「待人工核实」。
 *
 * ## 身份来源（产品接通后的关键修正）
 * 早期版本用 localStorage 假造 tenantId / userId，导致"谁在操作"无法归属。
 * 现在统一从登录会话取真实主体：``org_id`` → tenantId，``actor_id`` → userId
 * （二者均为后端用户的 UUID，满足业务端点的 UUID 校验）。未登录 / 凭据失效
 * 一律跳登录页，绝不退化成匿名假身份。
 */

"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { FormEvent, JSX } from "react";
import { useRouter } from "next/navigation";

import ChatMessage from "@/components/ChatMessage";
import {
  ApiRequestError,
  appendMessage,
  createConversation,
  getConversation,
} from "@/lib/chat";
import {
  getIdentityProvider,
  IdentityUnauthenticatedError,
} from "@/lib/identity";
import type {
  ChatMessageData,
  IntentSnapshot,
} from "@/types/chat";
import {
  AnalysisError,
  runAnalysis,
  saveAnalysisAddress,
  saveAnalysisResult,
  type AnalysisRequest,
  type ConsultationInput,
} from "@/lib/analysis";

interface LocalMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  intent?: IntentSnapshot;
  pendingVerification?: boolean;
  createdAt: string | null;
}

const CONVERSATION_STORAGE_KEY = "boip.consult.conversationId";

// 租户 / 用户身份改由登录会话提供（见下方 useEffect），不再用 localStorage 假 ID。

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
    value,
  );
}

function buildAssistantMessage(
  history: ChatMessageData[],
): LocalMessage | null {
  for (let idx = history.length - 1; idx >= 0; idx -= 1) {
    const row = history[idx];
    if (row.role === "assistant") {
      return {
        id: row.id,
        role: "assistant",
        content: row.content || "(无回复)",
        intent: (row.intent as IntentSnapshot) ?? undefined,
        pendingVerification:
          typeof (row.evidence as { pending_verification?: boolean })
            ?.pending_verification === "boolean"
            ? Boolean(
                (row.evidence as { pending_verification?: boolean })
                  .pending_verification,
              )
            : true,
        createdAt: row.created_at,
      };
    }
  }
  return null;
}

function buildConsultation(
  opening: string,
  budget: string,
  style: string,
): ConsultationInput | undefined {
  const consultation: ConsultationInput = {};
  if (opening.trim()) consultation.opening_preference = opening.trim();
  if (budget.trim()) consultation.budget_tier = budget.trim();
  if (style.trim()) consultation.style_preference = style.trim();
  return Object.keys(consultation).length > 0 ? consultation : undefined;
}

export default function ConsultPage(): JSX.Element {
  const router = useRouter();
  const [tenantId, setTenantId] = useState<string>("");
  const [userId, setUserId] = useState<string>("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [input, setInput] = useState<string>("");
  const [isSending, setIsSending] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  // 结构化需求字段（三 Agent 分析用，可选）。
  const [address, setAddress] = useState<string>("");
  const [regionHint, setRegionHint] = useState<string>("");
  const [openingPreference, setOpeningPreference] = useState<string>("");
  const [budgetTier, setBudgetTier] = useState<string>("");
  const [stylePreference, setStylePreference] = useState<string>("");

  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  // 取真实登录身份：org_id → tenantId，actor_id → userId。
  // 未登录 / 凭据失效 → 跳登录页；产品链路要求真实身份。
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const me = await getIdentityProvider().getIdentity();
        if (cancelled) return;
        if (!me.orgId || !me.actorId) {
          setError("登录身份缺少租户 / 用户标识，请重新登录。");
          return;
        }
        setTenantId(me.orgId);
        setUserId(me.actorId);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof IdentityUnauthenticatedError) {
          router.replace("/login");
          return;
        }
        setError("无法获取登录身份，请重新登录。");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  // 会话 ID 仅用于续接本地会话，仍存 localStorage；但租户 / 用户来自登录态。
  useEffect(() => {
    const stored = window.localStorage.getItem(CONVERSATION_STORAGE_KEY);
    if (stored && isUuid(stored)) {
      setConversationId(stored);
    }
  }, []);

  // Hydrate messages whenever we know a conversationId.
  useEffect(() => {
    if (!conversationId || !tenantId) return;
    let cancelled = false;
    void (async () => {
      try {
        const response = await getConversation(
          { tenantId, userId },
          conversationId,
        );
        if (cancelled) return;
        const hydrated: LocalMessage[] = response.messages.map(
          (row: ChatMessageData) => ({
            id: row.id,
            role: row.role === "user" ? "user" : "assistant",
            content: row.content,
            intent: (row.intent as IntentSnapshot) ?? undefined,
            pendingVerification:
              typeof (row.evidence as { pending_verification?: boolean })
                ?.pending_verification === "boolean"
                ? Boolean(
                    (row.evidence as { pending_verification?: boolean })
                      .pending_verification,
                  )
                : true,
            createdAt: row.created_at,
          }),
        );
        setMessages(hydrated);
      } catch (err) {
        if (cancelled) return;
        const detail =
          err instanceof ApiRequestError ? `${err.code}: ${err.message}` : String(err);
        setError(detail);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [conversationId, tenantId, userId]);

  // Auto-scroll on new message.
  useEffect(() => {
    if (!listRef.current) return;
    listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [messages]);

  const ensureConversation = useCallback(async (): Promise<string | null> => {
    if (conversationId && isUuid(conversationId)) return conversationId;
    const created = await createConversation(
      { tenantId, userId },
      { title: "BOIP 咨询会话" },
    );
    setConversationId(created.id);
    window.localStorage.setItem(CONVERSATION_STORAGE_KEY, created.id);
    return created.id;
  }, [conversationId, tenantId, userId]);

  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const text = input.trim();
      if (!text || isSending) return;
      if (!tenantId || !userId) {
        setError("租户 / 用户 ID 尚未就绪，请稍候。");
        return;
      }
      setError(null);
      setIsSending(true);
      const tempId = `local-${Date.now()}`;
      const optimistic: LocalMessage = {
        id: tempId,
        role: "user",
        content: text,
        createdAt: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, optimistic]);
      setInput("");
      try {
        const convId = await ensureConversation();
        if (!convId) {
          throw new ApiRequestError(
            "CONVERSATION_RESOLVE_FAILED",
            "无法创建或定位会话",
          );
        }
        const response = await appendMessage(
          { tenantId, userId },
          convId,
          { role: "user", content: text },
        );
        const assistant: LocalMessage = {
          id: response.message_id,
          role: "assistant",
          content: response.placeholder_reply || "(无回复)",
          intent: response.intent,
          pendingVerification: response.pending_verification,
          createdAt: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, assistant]);
      } catch (err) {
        const detail =
          err instanceof ApiRequestError ? `${err.code}: ${err.message}` : String(err);
        setError(detail);
        const failureMsg: LocalMessage = {
          id: `fail-${Date.now()}`,
          role: "assistant",
          content: "(本次请求失败，请稍后重试)",
          intent: { intent: "unknown", confidence: 0, method: "rule" },
          pendingVerification: true,
          createdAt: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, failureMsg]);
      } finally {
        setIsSending(false);
      }
    },
    [ensureConversation, input, isSending, tenantId, userId],
  );

  /**
   * 结构化需求 → 三 Agent 分析 → 结果页。
   * 收集地址 / 区域提示 / 偏好，调用 runAnalysis，结果写入 sessionStorage 后跳转。
   */
  const handleAnalyze = useCallback(async () => {
    if (isAnalyzing) return;
    setAnalysisError(null);
    setIsAnalyzing(true);

    const consultation = buildConsultation(
      openingPreference,
      budgetTier,
      stylePreference,
    );
    const payload: AnalysisRequest = {};
    if (address.trim()) payload.address = address.trim();
    if (regionHint.trim()) payload.region_hint = regionHint.trim();
    if (consultation) payload.consultation = consultation;

    try {
      const result = await runAnalysis(payload);
      saveAnalysisResult(result);
      saveAnalysisAddress(address.trim());
      router.push("/result");
    } catch (err) {
      const detail =
        err instanceof AnalysisError
          ? `${err.code}: ${err.message}`
          : err instanceof Error
            ? err.message
            : String(err);
      setAnalysisError(detail);
    } finally {
      setIsAnalyzing(false);
    }
  }, [address, regionHint, openingPreference, budgetTier, stylePreference, isAnalyzing, router]);

  const emptyHint = useMemo(
    () => "说点什么吧 — BOIP 会根据你的输入给出占位回复与意图标签。",
    [],
  );

  const hasAssistantHistory = useMemo(
    () => messages.some((m) => m.role === "assistant"),
    [messages],
  );

  const analyzeDisabled = useMemo(
    () => isAnalyzing,
    [isAnalyzing],
  );

  return (
    <section className="flex h-[calc(100vh-160px)] flex-col gap-4">
      <header className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-boip-primary-main">咨询</p>
          <h1 className="mt-1 text-2xl font-semibold text-slate-900">与 BOIP 聊聊你的项目</h1>
        </div>
        <span className="text-xs text-slate-400">
          会话 ID：{conversationId ?? "未创建"}
        </span>
      </header>

      <div
        ref={listRef}
        data-testid="message-list"
        className="flex-1 space-y-4 overflow-y-auto rounded-xl border border-slate-200 bg-slate-50 p-4"
      >
        {messages.length === 0 ? (
          <p className="text-center text-sm text-slate-500">{emptyHint}</p>
        ) : (
          messages.map((msg) => (
            <ChatMessage
              key={msg.id}
              id={msg.id}
              role={msg.role}
              content={msg.content}
              intent={msg.intent}
              pendingVerification={msg.pendingVerification ?? true}
              createdAt={msg.createdAt}
            />
          ))
        )}
      </div>

      {error ? (
        <p
          role="alert"
          data-testid="consult-error"
          className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700"
        >
          {error}
        </p>
      ) : null}

      <form
        onSubmit={handleSubmit}
        className="flex items-end gap-2"
        aria-label="发送新消息"
      >
        <label className="sr-only" htmlFor="consult-input">
          消息内容
        </label>
        <textarea
          id="consult-input"
          data-testid="consult-input"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          rows={2}
          placeholder="例如：我想新建一个门窗项目"
          className="flex-1 resize-none rounded-md border border-slate-300 bg-white p-2 text-sm focus:border-boip-primary-main focus:outline-none"
          disabled={isSending}
        />
        <button
          type="submit"
          data-testid="consult-send"
          disabled={isSending || input.trim().length === 0}
          className="rounded-md bg-boip-primary-main px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {isSending ? "发送中…" : "发送"}
        </button>
      </form>

      {!hasAssistantHistory ? (
        <p className="text-[11px] text-slate-400">
          所有回复均携带 <span className="font-mono">pending_verification</span> 标记，待真实 LLM 接入后将自动取消。
        </p>
      ) : null}

      {/* ---------------- 结构化需求 → 三 Agent 分析面板 ---------------- */}
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="mb-3">
          <p className="text-sm font-medium text-boip-primary-main">生成设计方案</p>
          <p className="mt-1 text-xs text-slate-400">
            填写以下可选信息，BOIP 将调用视觉 / 环境 / 设计三 Agent 生成分析报告。
          </p>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            地址（可选）
            <input
              id="consult-address"
              data-testid="consult-address"
              type="text"
              value={address}
              onChange={(event) => setAddress(event.target.value)}
              placeholder="例如：上海市浦东新区xx路"
              className="rounded-md border border-slate-300 bg-white p-2 text-sm focus:border-boip-primary-main focus:outline-none"
              disabled={isAnalyzing}
            />
          </label>

          <label className="flex flex-col gap-1 text-xs text-slate-600">
            小区 / 区域提示（可选）
            <input
              id="consult-region"
              data-testid="consult-region"
              type="text"
              value={regionHint}
              onChange={(event) => setRegionHint(event.target.value)}
              placeholder="例如：江浙沪、华南沿海"
              className="rounded-md border border-slate-300 bg-white p-2 text-sm focus:border-boip-primary-main focus:outline-none"
              disabled={isAnalyzing}
            />
          </label>

          <label className="flex flex-col gap-1 text-xs text-slate-600">
            开口偏好（可选）
            <input
              id="consult-opening"
              data-testid="consult-opening"
              type="text"
              value={openingPreference}
              onChange={(event) => setOpeningPreference(event.target.value)}
              placeholder="例如：大落地窗 / 通风为主"
              className="rounded-md border border-slate-300 bg-white p-2 text-sm focus:border-boip-primary-main focus:outline-none"
              disabled={isAnalyzing}
            />
          </label>

          <label className="flex flex-col gap-1 text-xs text-slate-600">
            预算档位（可选）
            <input
              id="consult-budget"
              data-testid="consult-budget"
              type="text"
              value={budgetTier}
              onChange={(event) => setBudgetTier(event.target.value)}
              placeholder="例如：经济 / 中高端"
              className="rounded-md border border-slate-300 bg-white p-2 text-sm focus:border-boip-primary-main focus:outline-none"
              disabled={isAnalyzing}
            />
          </label>

          <label className="flex flex-col gap-1 text-xs text-slate-600 sm:col-span-2">
            风格偏好（可选）
            <input
              id="consult-style"
              data-testid="consult-style"
              type="text"
              value={stylePreference}
              onChange={(event) => setStylePreference(event.target.value)}
              placeholder="例如：现代极简 / 新中式"
              className="rounded-md border border-slate-300 bg-white p-2 text-sm focus:border-boip-primary-main focus:outline-none"
              disabled={isAnalyzing}
            />
          </label>
        </div>

        {analysisError ? (
          <p
            role="alert"
            data-testid="consult-analysis-error"
            className="mt-3 rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700"
          >
            {analysisError}
          </p>
        ) : null}

        <button
          type="button"
          data-testid="consult-analyze"
          onClick={handleAnalyze}
          disabled={analyzeDisabled}
          className="mt-3 rounded-md bg-boip-primary-main px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {isAnalyzing ? "分析中…" : "生成设计方案"}
        </button>
      </div>
    </section>
  );
}

// NOTE: `buildAssistantMessage` is intentionally NOT re-exported from this page
// module. Next.js page modules must only export route-level symbols; re-exporting
// an internal helper triggers a `.next/types` page-constraint type error. The
// helper remains available for the in-page render flow.
