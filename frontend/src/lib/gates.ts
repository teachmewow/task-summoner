import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./api";

// Must stay in sync with ``GateState`` enum in backend/gates.py.
export type GateStateValue =
  | "needs_doc"
  | "writing_doc"
  | "in_doc_review"
  | "planning"
  | "in_plan_review"
  | "coding"
  | "in_code_review"
  | "done"
  | "manual_check";

export interface PrInfo {
  url: string;
  number: number;
  state: string;
  is_draft: boolean;
  head_branch: string;
}

export interface GateResponse {
  issue_key: string;
  state: GateStateValue;
  active_pr: PrInfo | null;
  retry_skill: string | null;
  reason: string;
  related_prs: PrInfo[];
  linear_status_type: string;
  linear_status_name: string;
  // One-sentence human-readable rationale emitted by the pre-gate skill.
  // ``null`` when the ticket hasn't run yet, or the skill skipped the
  // ``GATE_SUMMARY:`` contract. The ``GateCard`` renders a dimmed fallback
  // when absent so the layout doesn't shift.
  summary: string | null;
}

export interface GateActionResponse {
  ok: boolean;
  message: string;
  gh_output: string;
  resummoned_skill: string | null;
}

const gateKey = (key: string) => ["gate", key] as const;

export function useGate(issueKey: string | null) {
  return useQuery({
    queryKey: issueKey ? gateKey(issueKey) : ["gate", "__none__"],
    queryFn: () => apiFetch<GateResponse>(`/api/gates/${issueKey}`),
    enabled: !!issueKey,
    refetchOnWindowFocus: true,
    // Polled, not event-driven: refresh every 30s so the UI reflects GitHub
    // PR state changes without a webhook receiver.
    refetchInterval: 30_000,
    staleTime: 10_000,
  });
}

function invalidateIssueQueries(qc: ReturnType<typeof useQueryClient>, issueKey: string) {
  // After a gate action the FSM advances server-side and Linear flips its
  // status — invalidate every query that feeds the issue-detail page so the
  // user never has to hit a Refresh button. Gate, ticket context, and the
  // monitor listing all matter here.
  qc.invalidateQueries({ queryKey: gateKey(issueKey) });
  qc.invalidateQueries({ queryKey: ["tickets", issueKey] });
  qc.invalidateQueries({ queryKey: ["tickets"] });
}

export function useApproveGate(issueKey: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (pr_url: string) =>
      apiFetch<GateActionResponse>(`/api/gates/${issueKey}/approve`, {
        method: "POST",
        body: JSON.stringify({ pr_url }),
      }),
    onSuccess: () => invalidateIssueQueries(qc, issueKey),
  });
}

export function useRequestChangesGate(issueKey: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { pr_url: string; feedback: string; resummon_skill?: boolean }) =>
      apiFetch<GateActionResponse>(`/api/gates/${issueKey}/request-changes`, {
        method: "POST",
        body: JSON.stringify({
          pr_url: args.pr_url,
          feedback: args.feedback,
          resummon_skill: args.resummon_skill ?? true,
        }),
      }),
    onSuccess: () => invalidateIssueQueries(qc, issueKey),
  });
}

/** Human-friendly labels for the state chip. */
export const GATE_LABELS: Record<GateStateValue, string> = {
  needs_doc: "Needs doc?",
  writing_doc: "Writing doc",
  in_doc_review: "In doc review",
  planning: "Planning",
  in_plan_review: "In plan review",
  coding: "Coding",
  in_code_review: "In code review",
  done: "Done",
  manual_check: "Manual check needed",
};

/** Tailwind classes for the chip — keeps the 8 states visually distinct. */
export const GATE_CHIP_CLASSES: Record<GateStateValue, string> = {
  needs_doc: "border-soul-cyan/40 bg-soul-cyan/10 text-soul-cyan",
  writing_doc: "border-arise-violet/40 bg-arise-violet/10 text-arise-violet-bright",
  in_doc_review: "border-amber-flame/50 bg-amber-flame/10 text-amber-flame",
  planning: "border-arise-violet/40 bg-arise-violet/10 text-arise-violet-bright",
  in_plan_review: "border-amber-flame/50 bg-amber-flame/10 text-amber-flame",
  coding: "border-arise-violet/40 bg-arise-violet/10 text-arise-violet-bright",
  in_code_review: "border-amber-flame/50 bg-amber-flame/10 text-amber-flame",
  done: "border-mana-green/50 bg-mana-green/10 text-mana-green",
  manual_check: "border-ember-red/50 bg-ember-red/10 text-ember-red",
};

/** States that expose the lgtm / retry buttons. */
export function isReviewableState(state: GateStateValue): boolean {
  return state === "in_doc_review" || state === "in_plan_review" || state === "in_code_review";
}
