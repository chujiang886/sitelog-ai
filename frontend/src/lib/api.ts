"use client";

import type { ApiResponse } from "@/types/contracts";

const API_BASE_URL: string = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiRequestError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "ApiRequestError";
    this.code = code;
  }
}

export async function apiFetch<TData>(
  path: string,
  init: RequestInit = {},
): Promise<TData> {
  const response: Response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { Accept: "application/json", ...init.headers },
  });

  let payload: ApiResponse<TData>;
  try {
    payload = (await response.json()) as ApiResponse<TData>;
  } catch {
    throw new ApiRequestError("INVALID_RESPONSE", "API returned invalid JSON");
  }

  if (response.status === 401 && typeof window !== "undefined") {
    // Placeholder redirect: login flow will be wired in a later phase.
    window.location.assign("/login");
  }

  if (!response.ok || !payload.success) {
    if (!payload.success) {
      throw new ApiRequestError(payload.error.code, payload.error.message);
    }
    throw new ApiRequestError(`HTTP_${response.status}`, "API request failed");
  }
  return payload.data;
}

export function getApiBaseUrl(): string {
  "use client";
  return API_BASE_URL;
}
