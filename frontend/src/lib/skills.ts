import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./api";

export interface SkillSummary {
  name: string;
  description: string;
  user_invocable: boolean;
  path: string;
  modified_at: string;
}

export interface SkillsResponse {
  plugin_mode: string;
  plugin_path: string;
  resolved_from: string;
  editable: boolean;
  reason: string | null;
  skills: SkillSummary[];
}

export interface SkillDetail extends SkillSummary {
  content: string;
}

export interface SkillSaveResponse {
  ok: boolean;
  skill: SkillSummary;
}

const listKey = ["skills"] as const;
const detailKey = (name: string) => ["skills", name] as const;

export function useSkills() {
  return useQuery({
    queryKey: listKey,
    queryFn: () => apiFetch<SkillsResponse>("/api/skills"),
  });
}

export function useSkill(name: string | null) {
  return useQuery({
    queryKey: name ? detailKey(name) : ["skills", "__none__"],
    queryFn: () => apiFetch<SkillDetail>(`/api/skills/${name}`),
    enabled: !!name,
  });
}

export function useSaveSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { name: string; content: string }) =>
      apiFetch<SkillSaveResponse>(`/api/skills/${args.name}`, {
        method: "PUT",
        body: JSON.stringify({ content: args.content }),
      }),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: listKey });
      qc.invalidateQueries({ queryKey: detailKey(vars.name) });
    },
  });
}
