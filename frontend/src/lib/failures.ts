import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./api";

export interface FailureByPhase {
  phase: string;
  count: number;
}

export interface FailureByCategory {
  category: string;
  count: number;
  sample_message: string;
}

export interface FailedTicket {
  ticket_key: string;
  error: string;
  category: string;
  last_phase: string;
  retry_count: number;
  quarantined: boolean;
  updated_at: string;
  total_cost_usd: number;
}

export interface FailureSummary {
  total_failed: number;
  quarantined: number;
  healthy: number;
  by_phase: FailureByPhase[];
  by_category: FailureByCategory[];
  tickets: FailedTicket[];
}

export interface RetryResponse {
  ok: boolean;
  ticket_key: string;
  new_state: string;
}

const failuresKey = ["failures", "summary"] as const;

export function useFailureSummary() {
  return useQuery({
    queryKey: failuresKey,
    queryFn: () => apiFetch<FailureSummary>("/api/failures/summary"),
    refetchInterval: 10_000,
  });
}

export function useRetryTicket() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ticketKey: string) =>
      apiFetch<RetryResponse>(`/api/failures/${ticketKey}/retry`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: failuresKey }),
  });
}
