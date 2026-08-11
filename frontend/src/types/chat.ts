/**
 * Phase 1 / T06c — chat contract types.
 *
 * Shared between `lib/chat.ts` (API client) and the React chat components.
 * Mirrors backend `app/api/conversations.py` envelopes — any drift is a
 * cross-layer contract violation and must be fixed in this single file.
 */

import type { ApiResponse } from "@/types/contracts";
export type { ApiResponse };

export type ChatRole = "user" | "assistant" | "system";

export interface ConversationData {
  id: string;
  tenant_id: string;
  user_id: string;
  project_id: string | null;
  title: string;
  status: string;
  state: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface ChatMessageData {
  id: string;
  conversation_id: string;
  tenant_id: string;
  role: ChatRole;
  content: string;
  intent: Record<string, unknown>;
  evidence: Record<string, unknown>;
  created_at: string | null;
}

export type ConversationListItem = ChatMessageData;

export interface AgentStepSnapshot {
  name: string;
  status: string;
  pending_verification: boolean;
  notes: string[];
}

export interface IntentSnapshot {
  intent?: string;
  confidence?: number;
  method?: string;
  matched_keywords?: string[];
  rationale?: string;
}

export interface MessageAppendData {
  message_id: string;
  user_message_id: string;
  intent: IntentSnapshot;
  agent_steps: AgentStepSnapshot[];
  placeholder_reply: string;
  pending_verification: boolean;
}

export interface MessageListData {
  items: ChatMessageData[];
  total: number;
  page: number;
  page_size: number;
}

export type ChatEnvelope<T> = ApiResponse<T>;

export interface ChatFetchOptions {
  tenantId: string;
  userId: string;
}