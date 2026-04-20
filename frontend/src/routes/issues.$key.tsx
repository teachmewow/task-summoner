import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { GateCard } from "~/components/GateCard";
import { IssueActivityTimeline } from "~/components/IssueActivityTimeline";
import { PhaseStrip } from "~/components/PhaseStrip";
import { useGate } from "~/lib/gates";
import { useTicket } from "~/lib/issues";

/**
 * Per-issue detail view (REVAMP M3).
 *
 * Order is deliberately "decision → artifact tease → agent trace":
 *
 *  1. Header + ``PhaseStrip``      — where the mission is in the lifecycle.
 *  2. ``GateCard``                 — what the human needs to do right now.
 *  3. ``IssueActivityTimeline``    — the agent's full trace, below because
 *     it only matters when debugging or replaying.
 *
 * Typography follows the arcane vocabulary from the Claude Design bundle:
 * Geist Mono for identifiers (ticket key, branch name), Geist for prose,
 * an eyebrow above the title in uppercase Geist Mono.
 */
export const Route = createFileRoute("/issues/$key")({
  component: IssueDetail,
});

function IssueDetail() {
  const { key } = Route.useParams();
  const navigate = useNavigate();
  const ticket = useTicket(key);
  const gate = useGate(key);

  return (
    <section className="flex flex-col gap-6" data-route="issue-detail">
      <header className="flex flex-col gap-4">
        <button
          type="button"
          onClick={() => navigate({ to: "/monitor" })}
          data-issue-back
          className="inline-flex w-fit items-center gap-1.5 rounded-md border border-rune-line-strong bg-vault-soft px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-ghost-dim transition hover:border-arcane/50 hover:text-arcane focus:outline-none focus-visible:ring-2 focus-visible:ring-arcane/60"
        >
          <ArrowLeft size={11} strokeWidth={2} />
          Back to monitor
        </button>
        <div className="flex flex-col gap-0.5">
          <p className="font-mono text-[10px] uppercase tracking-wider text-arcane">
            Arcane Command Bridge
          </p>
          <div className="flex flex-wrap items-baseline gap-3">
            <h1 className="font-mono text-3xl font-semibold tracking-wider text-arcane">{key}</h1>
            <a
              href={`https://linear.app/issue/${key}`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 font-mono text-[11px] uppercase tracking-wider text-ghost-dim transition hover:text-arcane"
            >
              open in linear
              <ExternalLink size={10} strokeWidth={2} />
            </a>
          </div>
          {ticket.data ? (
            <p className="font-mono text-[11px] text-ghost-dimmer">
              <span className="text-ghost-dim">orchestrator</span>: {ticket.data.state}
              {ticket.data.branch_name ? (
                <>
                  <span className="px-1 text-ghost-dimmer">·</span>
                  <span className="text-ghost-dim">branch</span> {ticket.data.branch_name}
                </>
              ) : null}
            </p>
          ) : null}
        </div>
        <PhaseStrip orchestratorState={ticket.data?.state ?? null} />
      </header>

      {gate.data ? (
        <GateCard
          issueKey={key}
          gate={gate.data}
          onRefresh={() => gate.refetch()}
          isRefreshing={gate.isFetching}
          retryCount={ticket.data?.retry_count ?? 0}
        />
      ) : gate.isLoading ? (
        <p className="text-sm text-ghost-dim">Inferring gate state…</p>
      ) : gate.isError ? (
        <p className="text-sm text-blood">
          {gate.error instanceof Error ? gate.error.message : "Gate fetch failed"}
        </p>
      ) : null}

      <IssueActivityTimeline issueKey={key} />
    </section>
  );
}
