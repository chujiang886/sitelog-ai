/**
 * Phase 1 / T06c — ChatMessage bubble.
 *
 * Pure component: takes a message payload + optional intent metadata and
 * renders a styled bubble. The consult page owns state and only passes
 * already-resolved data to this component.
 */

import type { JSX } from "react";

import IntentBadge from "@/components/IntentBadge";
import type {
  ChatRole,
  IntentSnapshot,
} from "@/types/chat";

export interface ChatMessageProps {
  id: string;
  role: ChatRole;
  content: string;
  intent?: IntentSnapshot;
  pendingVerification?: boolean;
  createdAt?: string | null;
}

function bubbleClasses(role: ChatRole): string {
  if (role === "user") {
    return "bg-blue-600 text-white";
  }
  if (role === "assistant") {
    return "bg-white text-slate-900 ring-1 ring-slate-200";
  }
  return "bg-slate-100 text-slate-600";
}

function alignClasses(role: ChatRole): string {
  return role === "user" ? "items-end" : "items-start";
}

function roleLabel(role: ChatRole): string {
  if (role === "user") return "我";
  if (role === "assistant") return "BOIP";
  return "系统";
}

export default function ChatMessage(props: ChatMessageProps): JSX.Element {
  const isUser: boolean = props.role === "user";
  const showBadge: boolean = !isUser && Boolean(props.intent?.intent);
  const pending: boolean =
    typeof props.pendingVerification === "boolean"
      ? props.pendingVerification
      : true;

  return (
    <div
      data-testid="chat-message"
      data-role={props.role}
      className={`flex flex-col gap-1 ${alignClasses(props.role)}`}
    >
      <span className="text-xs text-slate-400">{roleLabel(props.role)}</span>
      <div
        className={`max-w-[80%] whitespace-pre-wrap break-words rounded-2xl px-4 py-2 text-sm shadow-sm ${bubbleClasses(props.role)}`}
      >
        {props.content}
      </div>
      {showBadge ? (
        <IntentBadge
          intent={props.intent?.intent}
          confidence={props.intent?.confidence}
          method={props.intent?.method}
          pendingVerification={pending}
        />
      ) : null}
    </div>
  );
}