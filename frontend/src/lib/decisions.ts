import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./api";

export interface DecisionSummary {
  filename: string;
  path: string;
  relative_path: string;
  title: string;
  summary: string;
  tags: string[];
  committed_at: string | null;
}

export interface DecisionsResponse {
  ok: boolean;
  configured: boolean;
  docs_repo: string | null;
  template_readme_url: string;
  decisions: DecisionSummary[];
  reason: string | null;
}

export interface OpenEditorResponse {
  ok: boolean;
  launcher: string;
  message: string;
}

const decisionsKey = (limit: number) => ["decisions", limit] as const;

export function useDecisions(limit = 10) {
  return useQuery({
    queryKey: decisionsKey(limit),
    queryFn: () =>
      apiFetch<DecisionsResponse>(`/api/decisions?limit=${encodeURIComponent(String(limit))}`),
    refetchOnWindowFocus: false,
    staleTime: 30_000,
  });
}

export function useRefreshDecisions() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["decisions"] });
}

export function useOpenDecision() {
  return useMutation({
    mutationFn: (path: string) =>
      apiFetch<OpenEditorResponse>("/api/decisions/open-editor", {
        method: "POST",
        body: JSON.stringify({ path }),
      }),
  });
}

/** Build a GitHub URL for a docs-repo file given the repo slug + relative path. */
export function githubUrlFor(slug: string, relativePath: string, branch = "main"): string {
  return `https://github.com/${slug}/blob/${branch}/${relativePath}`;
}
