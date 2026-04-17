export interface ConfigStatus {
  configured: boolean;
  errors: string[];
}

export interface TicketSummary {
  ticket_key: string;
  state: string;
  total_cost_usd: number;
  retry_count: number;
  updated_at: string;
  error?: string | null;
  mr_url?: string | null;
}
