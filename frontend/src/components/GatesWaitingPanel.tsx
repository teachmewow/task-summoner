import { Link } from "@tanstack/react-router";
import { ArrowUpRight, FileText, Hourglass } from "lucide-react";
import { useMemo, useState } from "react";
import { useTickets } from "~/lib/issues";
import { PlanPreviewModal } from "./PlanPreviewModal";
import { RfcPreviewModal } from "./RfcPreviewModal";

/**
 * Monitor-page sidebar that tracks tickets parked at a human-approval gate.
 *
 * Product intent: the Monitor page used to carry a "Recent Decisions" feed
 * built on the decisions-doc index. That was useful for a designer reading
 * a week's work, but the day-to-day workflow is "which tickets need my
 * lgtm right now?". This sidebar answers that directly: one row per ticket
 * whose ``state`` is ``WAITING_*_REVIEW``, with a quick link into the
 * issue page and the right Preview modal (RFC or Plan) keyed off the
 * state.
 *
 * We deliberately source from ``useTickets`` (the orchestrator's store)
 * rather than the gate endpoint. The monitor needs a *list*, not an
 * individual gate snapshot; hitting ``/api/gates/{key}`` per ticket would
 * be a fan-out we don't need. Ticket context already carries the artifact
 * PR URLs in ``metadata``.
 */
interface WaitingEntry {
  ticketKey: string;
  state: string;
  label: string;
  artifact: "rfc" | "plan";
  prUrl: string | null;
}

const STATE_LABELS: Record<string, { label: string; artifact: "rfc" | "plan" }> = {
  WAITING_DOC_REVIEW: { label: "Doc review", artifact: "rfc" },
  WAITING_PLAN_REVIEW: { label: "Plan review", artifact: "plan" },
  WAITING_MR_REVIEW: { label: "Code review", artifact: "plan" },
};

// Extracts the PR URL the gate action would operate on, mirroring the
// backend's ``_orchestrator_pr_url`` priority table so UI + server agree.
function prUrlFor(state: string, metadata: Record<string, unknown> | undefined): string | null {
  if (!metadata) return null;
  const key = state === "WAITING_DOC_REVIEW" ? "rfc_pr_url" : "plan_pr_url";
  const v = metadata[key];
  return typeof v === "string" && v.length > 0 ? v : null;
}

export function GatesWaitingPanel() {
  const { data, isLoading, isError, error } = useTickets();
  const [preview, setPreview] = useState<WaitingEntry | null>(null);

  const entries = useMemo<WaitingEntry[]>(() => {
    if (!data) return [];
    return data
      .filter((t) => t.state in STATE_LABELS)
      .map((t) => {
        const meta = STATE_LABELS[t.state];
        // `t.state in STATE_LABELS` guarantees this lookup is defined; the
        // `!` is a sanity-check, not a cast over a real maybe.
        if (!meta) throw new Error(`unreachable: state ${t.state} missing from labels`);
        return {
          ticketKey: t.ticket_key,
          state: t.state,
          label: meta.label,
          artifact: meta.artifact,
          prUrl: prUrlFor(t.state, t.metadata as Record<string, unknown> | undefined),
        };
      });
  }, [data]);

  return (
    <aside
      data-gates-waiting-panel
      className="flex flex-col gap-3 rounded-lg border border-shadow-purple/60 bg-void-800/70 p-5"
    >
      <header className="flex items-center gap-2">
        <Hourglass size={14} strokeWidth={2} className="text-amber-flame" />
        <h2 className="text-sm font-semibold uppercase tracking-wider text-arise-violet-bright">
          Gates waiting
        </h2>
      </header>

      {isLoading ? (
        <p className="text-xs text-soul-cyan/70">Loading tickets…</p>
      ) : isError ? (
        <p className="text-xs text-ember-red">
          {error instanceof Error ? error.message : "Failed to load tickets"}
        </p>
      ) : entries.length === 0 ? (
        <p className="text-xs text-soul-cyan/70">
          No tickets are waiting for review right now. When the orchestrator reaches a gate it will
          show up here.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {entries.map((e) => (
            <li
              key={e.ticketKey}
              className="flex flex-col gap-2 rounded-md border border-shadow-purple/60 bg-void-900/40 p-3"
            >
              <div className="flex items-center justify-between gap-2">
                <Link
                  to="/issues/$key"
                  params={{ key: e.ticketKey }}
                  className="flex items-center gap-1 text-sm font-medium text-ghost-white hover:text-arise-violet-bright"
                >
                  {e.ticketKey}
                  <ArrowUpRight size={12} strokeWidth={2} />
                </Link>
                <span className="rounded-full border border-amber-flame/40 bg-amber-flame/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-amber-flame">
                  {e.label}
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => setPreview(e)}
                  data-waiting-action="preview"
                  className="inline-flex items-center gap-1 rounded-md border border-arise-violet/50 bg-arise-violet/15 px-2 py-1 text-xs text-arise-violet-bright hover:bg-arise-violet/25"
                >
                  <FileText size={10} strokeWidth={2} />
                  Preview {e.artifact === "rfc" ? "RFC" : "plan"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* Single-instance modals — the panel never has more than one row
          "active" at a time, and keying them by ticketKey would mount N
          query subscriptions on Monitor page load. */}
      <RfcPreviewModal
        issueKey={preview?.ticketKey ?? ""}
        open={preview?.artifact === "rfc"}
        onClose={() => setPreview(null)}
        prUrl={preview?.prUrl ?? null}
      />
      <PlanPreviewModal
        issueKey={preview?.ticketKey ?? ""}
        open={preview?.artifact === "plan"}
        onClose={() => setPreview(null)}
        prUrl={preview?.prUrl ?? null}
      />
    </aside>
  );
}
