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
import { useTicket } from "~/lib/issues";
import { MOTION_CLASSES } from "~/lib/motion";
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

// Artifact visibility:
// - RFC still lives as a doc PR (docs repo), signalled via ``rfc_pr_url``
//   in metadata.
// - Plan lives as a local artifact only — the gate endpoint sets
//   ``gate.has_plan`` when ``artifacts/<key>/plan.md`` exists on disk.
// - Code PR = ``mr_url``, useful even after implementation as a
//   re-read of the shipped plan.
type Metadata = Record<string, unknown> | undefined;
const hasRfcArtifact = (m: Metadata) => typeof m?.rfc_pr_url === "string" && !!m.rfc_pr_url;

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
  const ticket = useTicket(issueKey);

  const isTerminal =
    !!gate.orchestrator_state && TERMINAL_ORCHESTRATOR_STATES.has(gate.orchestrator_state);
  // FSM wins over inference for the chip on terminal states. Otherwise
  // Linear-not-yet-caught-up races (e.g. the gate inference seeing a
  // MERGED code PR before Linear flips to Done) can flash MANUAL_CHECK
  // even though the orchestrator already closed out the ticket.
  const chipState: typeof gate.state = gate.orchestrator_state === "DONE" ? "done" : gate.state;
  const isPlanGate = gate.orchestrator_state === "WAITING_PLAN_REVIEW";
  const canPreviewRfc = hasRfcArtifact(ticket.data?.metadata);
  // Plan preview: trust the backend-computed ``has_plan`` (checks the
  // artifact exists on disk). Falls back to mr_url for the post-merge
  // case where users want to re-read the plan.
  const canPreviewPlan = gate.has_plan || !!ticket.data?.mr_url;

  // Reviewable iff the FSM is at an approval gate — never while terminal.
  const reviewable =
    !isTerminal &&
    (isReviewableOrchestratorState(gate.orchestrator_state) || isReviewableState(gate.state));
  // PR URL the buttons act on. For plan gates this is intentionally null —
  // no backing PR exists and the backend knows to skip ``gh pr merge``.
  const actionPrUrl = isPlanGate ? null : (gate.active_pr?.url ?? gate.orchestrator_pr_url ?? null);
  const chipClasses = GATE_CHIP_CLASSES[chipState] ?? GATE_CHIP_CLASSES.manual_check;

  const onApprove = () => {
    // Plan gates pass null; code/doc gates require a PR URL.
    if (!isPlanGate && !actionPrUrl) return;
    approve.mutate(actionPrUrl);
  };

  const onSubmitFeedback = (feedback: string) => {
    if (!isPlanGate && !actionPrUrl) return;
    requestChanges.mutate(
      { pr_url: actionPrUrl, feedback },
      {
        onSuccess: () => setModalOpen(false),
      },
    );
  };

  return (
    <section
      className={`flex flex-col gap-4 rounded-2xl border border-rune-line-strong bg-obsidian-raised p-5 glow-arcane-soft ${MOTION_CLASSES.runeIn}`}
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
            data-gate-chip={chipState}
          >
            {chipState === "manual_check" ? (
              <AlertTriangle size={12} strokeWidth={2} />
            ) : chipState === "done" ? (
              <CheckCircle2 size={12} strokeWidth={2} />
            ) : null}
            {GATE_LABELS[chipState] ?? chipState}
          </span>
          <span className="font-mono text-[10px] uppercase tracking-wider text-ghost-dim">
            linear: <span className="text-ghost/90">{gate.linear_status_name || "—"}</span>
          </span>
          {retryCount > 0 && !isTerminal ? (
            <span
              data-gate-attempt
              data-attempt-current={retryCount + 1}
              data-attempt-max={maxRetries}
              className="inline-flex items-center gap-1 rounded-full border border-ember/50 bg-ember/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-ember"
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
          className="inline-flex items-center gap-1.5 rounded-md border border-rune-line-strong bg-vault-soft px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-ghost-dim transition hover:border-arcane/50 hover:text-arcane disabled:opacity-50"
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
        <p data-gate-summary className="text-sm leading-relaxed text-ghost">
          {gate.summary}
        </p>
      ) : null}

      {chipState === "manual_check" && gate.reason ? (
        <div className="flex items-start gap-2 rounded-lg border-l-2 border-blood bg-blood/10 px-3 py-2 text-sm text-blood">
          <AlertTriangle size={14} strokeWidth={2} className="mt-0.5 shrink-0" />
          <span>{gate.reason}</span>
        </div>
      ) : null}

      {/* Plan gate has no backing PR (local artifact); skip this block
          entirely. Doc + code gates still surface the gating PR. */}
      {!isTerminal && !isPlanGate && gate.active_pr ? (
        <div className="flex flex-col gap-1">
          <span className="font-mono text-[10px] uppercase tracking-wider text-ghost-dim">
            active PR (gate)
          </span>
          <a
            href={gate.active_pr.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 font-mono text-sm text-arcane transition hover:text-arcane-300"
          >
            <span className="truncate">
              #{gate.active_pr.number}
              {gate.active_pr.is_draft ? " · draft" : ""} · {gate.active_pr.head_branch}
            </span>
            <ExternalLink size={12} strokeWidth={2} />
          </a>
        </div>
      ) : !isTerminal && !isPlanGate && actionPrUrl ? (
        <div className="flex flex-col gap-1">
          <span className="font-mono text-[10px] uppercase tracking-wider text-ghost-dim">
            active PR (gate)
          </span>
          <a
            href={actionPrUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 font-mono text-sm text-arcane transition hover:text-arcane-300"
          >
            <span className="truncate">{actionPrUrl}</span>
            <ExternalLink size={12} strokeWidth={2} />
          </a>
        </div>
      ) : null}

      {gate.related_prs.length > 0 ? (
        <div className="flex flex-col gap-1 font-mono text-[11px] text-ghost-dim">
          <span className="uppercase tracking-wider text-ghost-dimmer">related PRs</span>
          <ul className="flex flex-col gap-0.5">
            {gate.related_prs.map((pr) => (
              <li key={pr.url}>
                <a
                  href={pr.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 transition hover:text-arcane"
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
          {/* Plan gate shows the buttons even without a PR URL — the
              backend handles the gate transition purely via FSM. Doc and
              code gates still require a real PR URL. */}
          {reviewable && (isPlanGate || actionPrUrl) ? (
            <>
              <button
                type="button"
                onClick={onApprove}
                disabled={approve.isPending}
                data-gate-action="approve"
                className="inline-flex items-center gap-1.5 rounded-lg border border-phase-done/60 bg-phase-done/15 px-3 py-1.5 text-xs font-medium text-phase-done transition hover:bg-phase-done/25 disabled:cursor-not-allowed disabled:opacity-50"
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
                className="inline-flex items-center gap-1.5 rounded-lg border border-ember/50 bg-ember/15 px-3 py-1.5 text-xs font-medium text-ember transition hover:bg-ember/25 disabled:cursor-not-allowed disabled:opacity-50"
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
              className="inline-flex items-center gap-1.5 rounded-lg border border-arcane/50 bg-arcane/10 px-3 py-1.5 text-xs font-medium text-arcane transition hover:bg-arcane/20"
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
              className="inline-flex items-center gap-1.5 rounded-lg border border-arcane/50 bg-arcane/10 px-3 py-1.5 text-xs font-medium text-arcane transition hover:bg-arcane/20"
            >
              <FileText size={12} strokeWidth={2} />
              Preview Plan
            </button>
          ) : null}
          {reviewable && gate.retry_skill ? (
            <span className="font-mono text-[10px] uppercase tracking-wider text-ghost-dim">
              will re-summon <span className="text-arcane">{gate.retry_skill}</span>
            </span>
          ) : null}
        </div>
      ) : null}

      {approve.isError ? (
        <p className="text-xs text-blood">
          {approve.error instanceof Error ? approve.error.message : "Approve failed"}
        </p>
      ) : null}
      {approve.isSuccess && !isTerminal ? (
        <p className="text-xs text-phase-done">Merged. State advancing…</p>
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
      />

      <PlanPreviewModal
        issueKey={issueKey}
        open={planPreviewOpen}
        onClose={() => setPlanPreviewOpen(false)}
      />
    </section>
  );
}
