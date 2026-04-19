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

export interface LinearTeamSummary {
  id: string;
  name: string;
  key: string;
}

export interface LinearTeamsResponse {
  ok: boolean;
  message: string;
  teams: LinearTeamSummary[];
}

export function useFetchLinearTeams() {
  return useMutation({
    mutationFn: (api_key: string) =>
      apiFetch<LinearTeamsResponse>("/api/setup/linear-teams", {
        method: "POST",
        body: JSON.stringify({ api_key }),
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

// Mirrors MASKED_SECRET_SENTINEL on the backend — send this back on save when
// the user didn't touch a secret field and the backend preserves the on-disk
// value instead of overwriting with the mask literal.
export const MASKED_SECRET_SENTINEL = "********";

export interface SetupBoardSection {
  provider: "linear" | "jira" | "";
  api_key_masked: boolean;
  api_key: string | null;
  email: string | null;
  team_id: string;
  team_name: string;
  watch_label: string;
}

export interface SetupAgentSection {
  provider: "claude_code" | "codex" | "";
  auth_method: "personal_session" | "api_key" | "";
  api_key_masked: boolean;
  api_key: string | null;
  plugin_mode: "installed" | "local" | "";
  plugin_path: string;
}

export interface SetupRepoEntry {
  name: string;
  path: string;
}

export interface SetupGeneralSection {
  default_repo: string;
  polling_interval_sec: number;
  workspace_root: string;
  docs_repo: string;
}

export interface SetupStateResponse {
  board: SetupBoardSection;
  agent: SetupAgentSection;
  repos: SetupRepoEntry[];
  general: SetupGeneralSection;
}

export interface SetupSavePayload {
  board: Record<string, unknown>;
  agent: Record<string, unknown>;
  repos: SetupRepoEntry[];
  general: SetupGeneralSection;
}

export interface SetupSaveResponse {
  ok: boolean;
  config_path: string;
  docs_repo_saved: boolean;
  errors: string[];
}

export const setupStateKey = ["setup", "state"] as const;

export function useSetupState() {
  return useQuery({
    queryKey: setupStateKey,
    queryFn: () => apiFetch<SetupStateResponse>("/api/setup/state"),
    refetchOnWindowFocus: false,
  });
}

export function useSaveSetup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: SetupSavePayload) =>
      apiFetch<SetupSaveResponse>("/api/setup/save", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: configStatusKey });
      qc.invalidateQueries({ queryKey: setupStateKey });
    },
  });
}
