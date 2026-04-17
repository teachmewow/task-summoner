import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./api";

export interface CostByProfile {
  profile: string;
  cost_usd: number;
  turns: number;
  runs: number;
}

export interface CostByState {
  state: string;
  cost_usd: number;
  runs: number;
}

export interface CostByDay {
  date: string;
  cost_usd: number;
}

export interface CostByTicket {
  ticket_key: string;
  cost_usd: number;
  turns: number;
  runs: number;
  state: string;
  updated_at: string;
}

export interface TurnsBucket {
  bucket: string;
  count: number;
}

export interface BudgetStatus {
  monthly_budget_usd: number | null;
  month_spent_usd: number;
  remaining_usd: number | null;
  pct_used: number | null;
}

export interface CostSummary {
  total_cost_usd: number;
  ticket_count: number;
  run_count: number;
  avg_per_ticket_usd: number;
  budget: BudgetStatus;
  by_profile: CostByProfile[];
  by_state: CostByState[];
  by_day: CostByDay[];
  by_ticket: CostByTicket[];
  turns_histogram: TurnsBucket[];
}

export function useCostSummary() {
  return useQuery({
    queryKey: ["cost", "summary"] as const,
    queryFn: () => apiFetch<CostSummary>("/api/cost/summary"),
    refetchInterval: 10_000,
  });
}
