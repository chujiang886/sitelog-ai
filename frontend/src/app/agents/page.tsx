"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import type { AgentListData } from "@/types/contracts";

export default function AgentsPage(): JSX.Element {
  const [agents, setAgents] = useState<string[]>([]);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    let active: boolean = true;
    apiFetch<AgentListData>("/api/agents")
      .then((data: AgentListData) => {
        if (active) setAgents(data.agents);
      })
      .catch((requestError: unknown) => {
        if (active) setError(requestError instanceof Error ? requestError.message : "加载失败");
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <section>
      <p className="text-sm font-medium text-boip-primary-main">能力目录</p>
      <h1 className="mt-2 text-3xl font-semibold text-slate-900">Agent 列表</h1>
      {error ? <p className="mt-6 text-red-600">{error}</p> : null}
      <ul className="mt-6 grid gap-3 sm:grid-cols-2">
        {(agents.length > 0 ? agents : ["core", "environment", "vision", "design"]).map((agent: string) => (
          <li key={agent} className="rounded-lg border border-slate-200 bg-white p-4 text-slate-700">
            {agent}
          </li>
        ))}
      </ul>
    </section>
  );
}
