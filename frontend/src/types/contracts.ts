/** Shared API envelope and route contracts. */

export interface ApiError {
  code: string;
  message: string;
}

export interface SuccessEnvelope<TData> {
  success: true;
  data: TData;
}

export interface ErrorEnvelope {
  success: false;
  error: ApiError;
}

export type ApiResponse<TData> = SuccessEnvelope<TData> | ErrorEnvelope;

export interface HealthData {
  status: "ok";
  service: "frontend" | "backend";
  ts: string;
}

export type HealthResponse = SuccessEnvelope<HealthData>;

export interface ProjectListData {
  items: unknown[];
  total: number;
}

export type ProjectListResponse = SuccessEnvelope<ProjectListData>;

export interface KnowledgeRuleListData {
  items: unknown[];
  total: number;
}

export type KnowledgeRuleListResponse = SuccessEnvelope<KnowledgeRuleListData>;

export interface AgentListData {
  agents: string[];
}

export type AgentListResponse = SuccessEnvelope<AgentListData>;
