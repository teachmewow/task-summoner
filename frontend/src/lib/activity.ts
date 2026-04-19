import { apiFetch } from "./api";

/**
 * A single record from the per-ticket agent activity stream.
 *
 * The backend emits one record per line in ``artifacts/{KEY}/stream.jsonl``
 * (one object per adapter AgentEvent) and replays the full file before
 * tailing live. The UI renders markdown cards for ``message`` events and
 * collapsible boxes for ``tool_use`` / ``tool_result`` pairs.
 */
export type ActivityEventType = "message" | "tool_use" | "tool_result" | "error" | "completed";

export interface ActivityEvent {
  ts: string;
  type: ActivityEventType;
  content: string;
  agent: string;
  state?: string;
  tool_name?: string | null;
  tool_input?: Record<string, unknown> | null;
  tool_result?: string | null;
  tool_use_id?: string;
  is_error?: boolean | null;
  metadata?: Record<string, unknown>;
}

export async function fetchActivityHistory(issueKey: string): Promise<ActivityEvent[]> {
  return apiFetch<ActivityEvent[]>(`/api/issues/${issueKey}/events`);
}

export function activityStreamUrl(issueKey: string): string {
  return `/api/issues/${issueKey}/stream`;
}
