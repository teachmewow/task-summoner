import { useMutation, useQuery } from "@tanstack/react-query";
import { apiFetch } from "./api";

/**
 * Plan artifact — mirror of ``RfcResponse`` but backed by
 * ``artifacts/<key>/plan.md`` (orchestrator-owned filesystem) instead of
 * the user's docs repo. The frontend renders markdown client-side so the
 * wire shape is raw text + title metadata.
 */
export interface PlanResponse {
  ok: boolean;
  exists: boolean;
  issue_key: string;
  title: string;
  content: string;
  plan_path: string;
  reason: string | null;
}

export interface OpenEditorResponse {
  ok: boolean;
  launcher: string;
  message: string;
}

const planKey = (issueKey: string) => ["plan", issueKey] as const;

export function usePlan(issueKey: string | null) {
  return useQuery({
    queryKey: issueKey ? planKey(issueKey) : ["plan", "__none__"],
    queryFn: () => apiFetch<PlanResponse>(`/api/plans/${issueKey}`),
    enabled: !!issueKey,
    refetchOnWindowFocus: true,
    // Same cadence as the RFC query — cheap file read, matches gate polling.
    refetchInterval: 15_000,
    staleTime: 10_000,
  });
}

export function useOpenPlan(issueKey: string) {
  return useMutation({
    mutationFn: (path?: string) =>
      apiFetch<OpenEditorResponse>(`/api/plans/${issueKey}/open-editor`, {
        method: "POST",
        body: JSON.stringify({ path: path ?? "" }),
      }),
  });
}
