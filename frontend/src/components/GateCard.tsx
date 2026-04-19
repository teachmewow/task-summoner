import { AlertTriangle, CheckCircle2, ExternalLink, Loader2, RefreshCw } from "lucide-react";
import { useState } from "react";
import {
  GATE_CHIP_CLASSES,
  GATE_LABELS,
  type GateResponse,
  isReviewableState,
  useApproveGate,
  useRequestChangesGate,
} from "~/lib/gates";
import { RequestChangesModal } from "./RequestChangesModal";

interface Props {
  issueKey: string;
  gate: GateResponse;
  onRefresh: () => void;
  isRefreshing: boolean;
}

export function GateCard({ issueKey, gate, onRefresh, isRefreshing }: Props) {
  const [modalOpen, setModalOpen] = useState(false);
  const approve = useApproveGate(issueKey);
  const requestChanges = useRequestChangesGate(issueKey);

  const reviewable = isReviewableState(gate.state);
  const chipClasses = GATE_CHIP_CLASSES[gate.state] ?? GATE_CHIP_CLASSES.manual_check;

  const onApprove = () => {
    if (!gate.active_pr) return;
    approve.mutate(gate.active_pr.url);
  };

  const onSubmitFeedback = (feedback: string) => {
    if (!gate.active_pr) return;
    requestChanges.mutate(
      { pr_url: gate.active_pr.url, feedback },
      {
        onSuccess: () => setModalOpen(false),
      },
    );
  };

  return (
    <section
      className="flex flex-col gap-4 rounded-lg border border-shadow-purple/60 bg-void-800/70 p-5"
      data-gate-card
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

      {gate.state === "manual_check" && gate.reason ? (
        <div className="flex items-start gap-2 rounded-md border border-ember-red/40 bg-ember-red/10 px-3 py-2 text-sm text-ember-red">
          <AlertTriangle size={14} strokeWidth={2} className="mt-0.5 shrink-0" />
          <span>{gate.reason}</span>
        </div>
      ) : null}

      {gate.active_pr ? (
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

      {reviewable && gate.active_pr ? (
        <div className="flex flex-wrap items-center gap-2 pt-2">
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
          {gate.retry_skill ? (
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
      {approve.isSuccess ? (
        <p className="text-xs text-mana-green">Approved. Refresh to see the new state.</p>
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
    </section>
  );
}
