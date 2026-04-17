import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./api";

export interface ConfigStatus {
  configured: boolean;
  errors: string[];
}

export interface ConfigPayload {
  board_type: "linear" | "jira";
  board_config: Record<string, string>;
  agent_type: "claude_code" | "codex";
  agent_config: Record<string, string>;
  repos: Record<string, string>;
  default_repo: string;
  polling_interval_sec: number;
  workspace_root: string;
}

export interface ConfigTestResponse {
  ok: boolean;
  message: string;
}

export interface ConfigSaveResponse {
  ok: boolean;
  path: string;
}

export const configStatusKey = ["config", "status"] as const;

export function useConfigStatus() {
  return useQuery({
    queryKey: configStatusKey,
    queryFn: () => apiFetch<ConfigStatus>("/api/config/status"),
    refetchOnWindowFocus: false,
    staleTime: 5_000,
  });
}

export function useTestConfig() {
  return useMutation({
    mutationFn: (payload: ConfigPayload) =>
      apiFetch<ConfigTestResponse>("/api/config/test", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
  });
}

export function useSaveConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ConfigPayload) =>
      apiFetch<ConfigSaveResponse>("/api/config", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: configStatusKey }),
  });
}
