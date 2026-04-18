import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./api";

export interface BoardHealth {
  provider: string;
  configured: boolean;
  watch_label: string;
  identifier: string;
  last_ok_at: string | null;
  last_error: string | null;
}

export interface AgentHealth {
  provider: string;
  session_available: boolean;
  plugin_mode: string;
  plugin_path: string;
  plugin_resolved: boolean;
  plugin_reason: string | null;
}

export interface LocalStateHealth {
  total_tickets: number;
  active_tickets: number;
  terminal_tickets: number;
  workspace_root: string;
  workspace_bytes: number;
  artifacts_dir: string;
  artifacts_bytes: number;
}

export interface HealthResponse {
  board: BoardHealth;
  agent: AgentHealth;
  local: LocalStateHealth;
}

export interface TestBoardResponse {
  ok: boolean;
  message: string;
  sample_count: number;
}

export interface CleanResponse {
  ok: boolean;
  scanned: number;
  removed: string[];
  message: string;
}

const healthKey = ["health"] as const;

export function useHealth() {
  return useQuery({
    queryKey: healthKey,
    queryFn: () => apiFetch<HealthResponse>("/api/health"),
    refetchInterval: 10_000,
  });
}

export function useTestBoard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<TestBoardResponse>("/api/health/test-board", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: healthKey }),
  });
}

export function useClean() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<CleanResponse>("/api/health/clean", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: healthKey }),
  });
}
