import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./api";

export interface AgentProfile {
  name: string;
  model: string;
  max_turns: number;
  max_budget_usd: number;
  tools: string[];
  enabled: boolean;
}

export interface AgentProfilesResponse {
  agent_provider: string;
  available_models: string[];
  profiles: AgentProfile[];
}

export interface AgentProfilePayload {
  model: string;
  max_turns: number;
  max_budget_usd: number;
  tools: string[];
  enabled: boolean;
}

export interface AgentProfileSaveResponse {
  ok: boolean;
  profile: AgentProfile;
}

const key = ["agent-profiles"] as const;

export function useAgentProfiles() {
  return useQuery({
    queryKey: key,
    queryFn: () => apiFetch<AgentProfilesResponse>("/api/agent-profiles"),
  });
}

export function useSaveAgentProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { name: string; payload: AgentProfilePayload }) =>
      apiFetch<AgentProfileSaveResponse>(`/api/agent-profiles/${args.name}`, {
        method: "POST",
        body: JSON.stringify(args.payload),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
  });
}
