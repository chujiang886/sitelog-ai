/**
 * Phase 1 / T06c — chat API client.
 *
 * Wraps `apiFetch` with chat-specific envelope contracts so React components
 * never touch raw HTTP. All call sites must destructure `{success, data}`
 * after awaiting; missing/empty responses raise `ApiRequestError`.
 */

import { apiFetch, ApiRequestError } from "@/lib/api";
import type {
  ApiResponse,
  ConversationData,
  ConversationListItem,
  MessageAppendData,
  MessageListData,
} from "@/types/chat";

export interface CreateConversationInput {
  projectId?: string;
  title?: string;
}

export interface AppendMessageInput {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface ChatTenantContext {
  tenantId: string;
  userId: string;
}

function buildHeaders(context: ChatTenantContext): Record<string, string> {
  return {
    "X-Tenant-Id": context.tenantId,
    "X-User-Id": context.userId,
  };
}

/**
 * Create a new conversation. Backend returns the freshly persisted
 * conversation row; `data.project_id` may be `null` when not bound to a project.
 */
export async function createConversation(
  context: ChatTenantContext,
  input: CreateConversationInput = {},
): Promise<ConversationData> {
  const response = await apiFetch<ConversationData>(
    "/api/conversations",
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...buildHeaders(context) },
      body: JSON.stringify({
        project_id: input.projectId ?? null,
        title: input.title ?? null,
      }),
    },
  );
  return response;
}

/**
 * Fetch a single conversation and its complete message history.
 */
export async function getConversation(
  context: ChatTenantContext,
  conversationId: string,
): Promise<{ conversation: ConversationData; messages: ConversationListItem[] }> {
  return apiFetch(`/api/conversations/${conversationId}`, {
    method: "GET",
    headers: buildHeaders(context),
  });
}

/**
 * Append a message to a conversation. The Core Agent chat pipeline runs
 * server-side and the response carries the assistant `message_id`,
 * NLU `intent`, `agent_steps`, and `pending_verification`.
 */
export async function appendMessage(
  context: ChatTenantContext,
  conversationId: string,
  input: AppendMessageInput,
): Promise<MessageAppendData> {
  return apiFetch<MessageAppendData>(
    `/api/conversations/${conversationId}/messages`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...buildHeaders(context) },
      body: JSON.stringify({ role: input.role, content: input.content }),
    },
  );
}

/**
 * Paginated list of messages for a conversation.
 */
export async function listMessages(
  context: ChatTenantContext,
  conversationId: string,
  page: number = 1,
  pageSize: number = 50,
): Promise<MessageListData> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  return apiFetch<MessageListData>(
    `/api/conversations/${conversationId}/messages?${params.toString()}`,
    {
      method: "GET",
      headers: buildHeaders(context),
    },
  );
}

export { ApiRequestError };
export type { ApiResponse };