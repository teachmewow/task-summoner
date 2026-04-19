import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./api";

// Mirrors ``TicketContext`` on the backend — enough for the cluster-6 UI.
export interface TicketContext {
  ticket_key: string;
  state: string;
  created_at: string;
  updated_at: string;
  branch_name: string | null;
  workspace_path: string | null;
  mr_url: string | null;
  retry_count: number;
  total_cost_usd: number;
  error: string | null;
  metadata?: Record<string, unknown>;
}

const ticketsKey = ["tickets"] as const;
const ticketKey = (key: string) => ["tickets", key] as const;

export function useTickets() {
  return useQuery({
    queryKey: ticketsKey,
    queryFn: () => apiFetch<TicketContext[]>("/api/tickets"),
    refetchOnWindowFocus: false,
    staleTime: 5_000,
  });
}

export function useTicket(key: string | null) {
  return useQuery({
    queryKey: key ? ticketKey(key) : ["tickets", "__none__"],
    queryFn: () => apiFetch<TicketContext>(`/api/tickets/${key}`),
    enabled: !!key,
  });
}
