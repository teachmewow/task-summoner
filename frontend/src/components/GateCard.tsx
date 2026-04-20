import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  FileText,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { useState } from "react";
import {
  GATE_CHIP_CLASSES,
  GATE_LABELS,
  type GateResponse,
  isReviewableOrchestratorState,
  isReviewableState,
  useApproveGate,
  useRequestChangesGate,
} from "~/lib/gates";
import { PlanPreviewModal } from "./PlanPreviewModal";
import { RequestChangesModal } from "./RequestChangesModal";
import { RfcPreviewModal } from "./RfcPreviewModal";

interface Props {
  issueKey: string;
  gate: GateResponse;
  onRefresh: () => void;
  isRefreshing: boolean;
  // When the orchestrator is actively retrying a state, ``retryCount`` is
  // positive and the card surfaces an "Attempt N of M" counter next to the
  // gate chip. Passed from the enclosing route via ``TicketContext``.
  retryCount?: number;
  maxRetries?: number;
}

// Orchestrator states where the ticket is already closed out — no more
// actions, no stale "ready-for-review" banner needed. We still render
// Preview buttons so the user can re-read what shipped.
const TERMINAL_ORCHESTRATOR_STATES = new Set(["DONE", "FAILED"]);

// Orchestrator states where the RFC artifact plausibly exists. ``QUEUED``
// / ``CHECKING_DOC`` / ``CREATING_DOC`` still have no RFC drafted; after
// the doc gate the RFC is always present on the doc-path flow.
const RFC_PREVIEWABLE_STATES = new Set([
  "WAITING_DOC_REVIEW",
  "IMPROVING_DOC",
  "PLANNING",
  "WAITING_PLAN_REVIEW",
  "IMPLEMENTING",
  "WAITING_MR_REVIEW",
  "FIXING_MR",
  "DONE",
]);

// Orchestrator states where ``plan.md`` plausibly exists on disk.
const PLAN_PREVIEWABLE_STATES = new Set([
  "WAITING_PLAN_REVIEW",
  "IMPLEMENTING",
  "WAITING_MR_REVIEW",
  "FIXING_MR",
  "DONE",
]);

export function GateCard({
  issueKey,
  gate,
  onRefresh,
  isRefreshing,
  retryCount = 0,
  maxRetries = 3,
}: Props) {
  const [modalOpen, setModalOpen] = useState(false);
  const [rfcPreviewOpen, setRfcPreviewOpen] = useState(false);
  const [planPreviewOpen, setPlanPreviewOpen] = useState(false);
  const approve = useApproveGate(issueKey);
  const requestChanges = useRequestChangesGate(issueKey);

  const isTerminal =
    !!gate.orchestrator_state && TERMINAL_ORCHESTRATOR_STATES.has(gate.orchestrator_state);
  const canPreviewRfc =
    !!gate.orchestrator_state && RFC_PREVIEWABLE_STATES.has(gate.orchestrator_state);
  const canPreviewPlan =
    !!gate.orchestrator_state && PLAN_PREVIEWABLE_STATES.has(gate.orchestrator_state);

  // Reviewable iff the FSM is at an approval gate — never while terminal.
  const reviewable =
    !isTerminal &&
    (isReviewableOrchestratorState(gate.orchestrator_state) || isReviewableState(gate.state));
  // PR URL the buttons act on — inference first (has metadata like draft /
  // headBranch), orchestrator fallback second (the URL the skill opened when
  // inference can't find it due to repo scope).
  const actionPrUrl = gate.active_pr?.url ?? gate.orchestrator_pr_url ?? null;
  const chipClasses = GATE_CHIP_CLASSES[gate.state] ?? GATE_CHIP_CLASSES.manual_check;

  const onApprove = () => {
    if (!actionPrUrl) return;
    approve.mutate(actionPrUrl);
  };

  const onSubmitFeedback = (feedback: string) => {
    if (!actionPrUrl) return;
    requestChanges.mutate(
      { pr_url: actionPrUrl, feedback },
      {
        onSuccess: () => setModalOpen(false),
      },
    );
  };

  return (
    <section
      className="flex flex-col gap-4 rounded-lg border border-shadow-purple/60 bg-void-800/70 p-5"
      data-gate-card
      data-gate-terminal={isTerminal ? "true" : "false"}
    >
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span
            className={[
              "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
              chipClasses,
            ].join(" ")}
            data-gate-chip={gate.state}
          >
            {gate.state === "manual_check" ? (
              <AlertTriangle size={12} strokeWidth={2} />
            ) : gate.state === "done" ? (
              <CheckCircle2 size={12} strokeWidth={2} />
            ) : null}
            {GATE_LABELS[gate.state] ?? gate.state}
          </span>
          <span className="text-xs text-soul-cyan/70">
            Linear: <code className="text-ghost-white/90">{gate.linear_status_name || "—"}</code>
          </span>
          {retryCount > 0 && !isTerminal ? (
            <span
              data-gate-attempt
              data-attempt-current={retryCount + 1}
              data-attempt-max={maxRetries}
              className="inline-flex items-center gap-1 rounded-full border border-amber-flame/50 bg-amber-flame/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-amber-flame"
            >
              <RefreshCw size={10} strokeWidth={2} />
              Attempt {Math.min(retryCount + 1, maxRetries)} of {maxRetries}
            </span>
          ) : null}
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={isRefreshing}
          className="inline-flex items-center gap-1.5 rounded-md border border-shadow-purple/60 bg-void-900/60 px-2.5 py-1 text-xs text-soul-cyan transition hover:border-arise-violet/50 hover:text-ghost-white disabled:opacity-50"
          title="Refresh PR state"
        >
          <RefreshCw
            size={12}
            strokeWidth={2}
            className={isRefreshing ? "animate-spin" : undefined}
          />
          Refresh
        </button>
      </header>

      {/* The gate summary is review-time context — once the ticket is DONE
          or FAILED it's stale (talks about "ready-for-review") and just adds
          noise. Hide it on terminal states. */}
      {!isTerminal && gate.summary ? (
        <p data-gate-summary className="text-sm leading-relaxed text-ghost-white/90">
          {gate.summary}
        </p>
      ) : null}

      {gate.state === "manual_check" && gate.reason ? (
        <div className="flex items-start gap-2 rounded-md border border-ember-red/40 bg-ember-red/10 px-3 py-2 text-sm text-ember-red">
          <AlertTriangle size={14} strokeWidth={2} className="mt-0.5 shrink-0" />
          <span>{gate.reason}</span>
        </div>
      ) : null}

      {!isTerminal && gate.active_pr ? (
        <div className="flex flex-col gap-1 text-sm">
          <span className="text-xs uppercase tracking-wider text-soul-cyan/60">
            Active PR (gate)
          </span>
          <a
            href={gate.active_pr.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 text-arise-violet-bright hover:text-ghost-white"
          >
            <span className="truncate">
              #{gate.active_pr.number}
              {gate.active_pr.is_draft ? " · draft" : ""} · {gate.active_pr.head_branch}
            </span>
            <ExternalLink size={12} strokeWidth={2} />
          </a>
        </div>
      ) : !isTerminal && actionPrUrl ? (
        <div className="flex flex-col gap-1 text-sm">
          <span className="text-xs uppercase tracking-wider text-soul-cyan/60">
            Active PR (gate)
          </span>
          <a
            href={actionPrUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 text-arise-violet-bright hover:text-ghost-white"
          >
            <span className="truncate">{actionPrUrl}</span>
            <ExternalLink size={12} strokeWidth={2} />
          </a>
        </div>
      ) : null}

      {gate.related_prs.length > 0 ? (
        <div className="flex flex-col gap-1 text-xs text-soul-cyan/70">
          <span className="uppercase tracking-wider">Related PRs</span>
          <ul className="flex flex-col gap-0.5">
            {gate.related_prs.map((pr) => (
              <li key={pr.url}>
                <a
                  href={pr.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 hover:text-ghost-white"
                >
                  #{pr.number} · {pr.state.toLowerCase()}
                  {pr.is_draft ? " · draft" : ""} · {pr.head_branch}
                  <ExternalLink size={10} strokeWidth={2} />
                </a>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Actions + Preview buttons. Preview is available whenever the
          artifact exists (including after DONE for re-read); the approval
          buttons only show at a real review gate. */}
      {reviewable || canPreviewRfc || canPreviewPlan ? (
        <div className="flex flex-wrap items-center gap-2 pt-2">
          {reviewable && actionPrUrl ? (
            <>
              <button
                type="button"
                onClick={onApprove}
                disabled={approve.isPending}
                data-gate-action="approve"
                className="inline-flex items-center gap-1.5 rounded-md border border-mana-green/60 bg-mana-green/15 px-3 py-1.5 text-xs font-medium text-mana-green transition hover:bg-mana-green/25 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {approve.isPending ? (
                  <Loader2 size={12} strokeWidth={2} className="animate-spin" />
                ) : (
                  <CheckCircle2 size={12} strokeWidth={2} />
                )}
                lgtm
              </button>
              <button
                type="button"
                onClick={() => setModalOpen(true)}
                disabled={requestChanges.isPending}
                data-gate-action="request-changes"
                className="inline-flex items-center gap-1.5 rounded-md border border-amber-flame/50 bg-amber-flame/15 px-3 py-1.5 text-xs font-medium text-amber-flame transition hover:bg-amber-flame/25 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <RefreshCw size={12} strokeWidth={2} />
                Retry with feedback
              </button>
            </>
          ) : null}
          {canPreviewRfc ? (
            <button
              type="button"
              onClick={() => setRfcPreviewOpen(true)}
              data-gate-action="preview-rfc"
              className="inline-flex items-center gap-1.5 rounded-md border border-arise-violet/50 bg-arise-violet/15 px-3 py-1.5 text-xs font-medium text-arise-violet-bright transition hover:bg-arise-violet/25"
            >
              <FileText size={12} strokeWidth={2} />
              Preview RFC
            </button>
          ) : null}
          {canPreviewPlan ? (
            <button
              type="button"
              onClick={() => setPlanPreviewOpen(true)}
              data-gate-action="preview-plan"
              className="inline-flex items-center gap-1.5 rounded-md border border-arise-violet/50 bg-arise-violet/15 px-3 py-1.5 text-xs font-medium text-arise-violet-bright transition hover:bg-arise-violet/25"
            >
              <FileText size={12} strokeWidth={2} />
              Preview Plan
            </button>
          ) : null}
          {reviewable && gate.retry_skill ? (
            <span className="text-xs text-soul-cyan/60">
              Will re-summon <code className="text-ghost-white/90">{gate.retry_skill}</code>
            </span>
          ) : null}
        </div>
      ) : null}

      {approve.isError ? (
        <p className="text-xs text-ember-red">
          {approve.error instanceof Error ? approve.error.message : "Approve failed"}
        </p>
      ) : null}
      {approve.isSuccess && !isTerminal ? (
        <p className="text-xs text-mana-green">Merged. State advancing…</p>
      ) : null}

      <RequestChangesModal
        open={modalOpen}
        skillName={gate.retry_skill}
        onClose={() => setModalOpen(false)}
        onSubmit={onSubmitFeedback}
        isPending={requestChanges.isPending}
        error={
          requestChanges.isError
            ? requestChanges.error instanceof Error
              ? requestChanges.error.message
              : "Failed"
            : null
        }
      />

      <RfcPreviewModal
        issueKey={issueKey}
        open={rfcPreviewOpen}
        onClose={() => setRfcPreviewOpen(false)}
        prUrl={gate.orchestrator_pr_url ?? gate.active_pr?.url ?? null}
      />

      <PlanPreviewModal
        issueKey={issueKey}
        open={planPreviewOpen}
        onClose={() => setPlanPreviewOpen(false)}
        prUrl={gate.orchestrator_pr_url ?? gate.active_pr?.url ?? null}
      />
    </section>
  );
}
