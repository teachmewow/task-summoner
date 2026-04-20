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
  // FSM state read directly from the orchestrator. This is the authoritative
  // "is this a gate?" signal — every ``WAITING_*_REVIEW`` should surface the
  // lgtm/retry buttons, independent of whether PR inference found the
  // underlying PR (which can fail when the PR lives on a non-default repo).
  orchestrator_state: string | null;
  // PR URL the orchestrator stashed for the current state — used as the
  // fallback when ``active_pr`` is null (e.g. plan PR on a repo outside
  // ``default_repo``). ``null`` when the state doesn't expect a PR.
  orchestrator_pr_url: string | null;
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
  // user never has to hit a Refresh button. Gate, ticket context, artifacts
  // (rfc + plan), and the monitor listing all matter here.
  qc.invalidateQueries({ queryKey: gateKey(issueKey) });
  qc.invalidateQueries({ queryKey: ["tickets", issueKey] });
  qc.invalidateQueries({ queryKey: ["tickets"] });
  qc.invalidateQueries({ queryKey: ["rfc", issueKey] });
  qc.invalidateQueries({ queryKey: ["plan", issueKey] });
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

/**
 * Arcane chip classes — one per inferred gate state. The four pipeline
 * phases map to the design's phase-color tokens (doc = amber,
 * plan = rune violet, implement = arcane cyan, done = mana green).
 * Action-needed (review + manual_check) uses ember amber so the human's
 * attention goes to "something's waiting on me".
 */
export const GATE_CHIP_CLASSES: Record<GateStateValue, string> = {
  needs_doc: "border-phase-doc/40 bg-phase-doc/10 text-phase-doc",
  writing_doc: "border-phase-doc/40 bg-phase-doc/10 text-phase-doc",
  in_doc_review: "border-ember/50 bg-ember/10 text-ember",
  planning: "border-phase-plan/40 bg-phase-plan/10 text-phase-plan",
  in_plan_review: "border-ember/50 bg-ember/10 text-ember",
  coding: "border-phase-code/40 bg-phase-code/10 text-phase-code",
  in_code_review: "border-ember/50 bg-ember/10 text-ember",
  done: "border-phase-done/50 bg-phase-done/10 text-phase-done",
  manual_check: "border-blood/50 bg-blood/10 text-blood",
};

/** States that expose the lgtm / retry buttons. */
export function isReviewableState(state: GateStateValue): boolean {
  return state === "in_doc_review" || state === "in_plan_review" || state === "in_code_review";
}

/**
 * FSM states that definitively require a human review decision. The
 * orchestrator is the source of truth — every ``WAITING_*_REVIEW`` maps to
 * a gate, regardless of whether the PR inference layer (``gh search``) was
 * able to locate the underlying PR. Previously the UI gated its own buttons
 * on ``isReviewableState`` which only considered inferred state, producing
 * silent "no buttons" outcomes when the PR was on a non-default repo.
 */
export function isReviewableOrchestratorState(state: string | null): boolean {
  return (
    state === "WAITING_DOC_REVIEW" ||
    state === "WAITING_PLAN_REVIEW" ||
    state === "WAITING_MR_REVIEW"
  );
}
