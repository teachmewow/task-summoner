import { useMutation, useQuery } from "@tanstack/react-query";
import { apiFetch } from "./api";

export interface RfcResponse {
  ok: boolean;
  exists: boolean;
  issue_key: string;
  title: string;
  content: string;
  readme_path: string;
  images: string[];
  reason: string | null;
}

export interface OpenEditorResponse {
  ok: boolean;
  launcher: string;
  message: string;
}

const rfcKey = (issueKey: string) => ["rfc", issueKey] as const;

export function useRfc(issueKey: string | null) {
  return useQuery({
    queryKey: issueKey ? rfcKey(issueKey) : ["rfc", "__none__"],
    queryFn: () => apiFetch<RfcResponse>(`/api/rfcs/${issueKey}`),
    enabled: !!issueKey,
    refetchOnWindowFocus: true,
    // Poll every 15s so the RFC panel picks up a newly-created doc without
    // the user having to reload. The endpoint is a cheap file read; the gate
    // queries already poll at 30s so this doesn't change the ambient traffic
    // profile meaningfully.
    refetchInterval: 15_000,
    staleTime: 10_000,
  });
}

export function useOpenRfc(issueKey: string) {
  return useMutation({
    mutationFn: (path?: string) =>
      apiFetch<OpenEditorResponse>(`/api/rfcs/${issueKey}/open-editor`, {
        method: "POST",
        body: JSON.stringify({ path: path ?? "" }),
      }),
  });
}

/** Build the ``/api/rfcs/{key}/image/{name}`` URL for inline rendering. */
export function rfcImageUrl(issueKey: string, name: string): string {
  return `/api/rfcs/${encodeURIComponent(issueKey)}/image/${encodeURIComponent(name)}`;
}
