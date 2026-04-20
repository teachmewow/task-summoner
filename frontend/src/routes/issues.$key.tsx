import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { GateCard } from "~/components/GateCard";
import { IssueActivityTimeline } from "~/components/IssueActivityTimeline";
import { PlanPanel } from "~/components/PlanPanel";
import { RfcPanel } from "~/components/RfcPanel";
import { useGate } from "~/lib/gates";
import { useTicket } from "~/lib/issues";

/**
 * Per-issue detail view.
 *
 * Order is deliberately "decision → artifact → agent trace":
 *
 *  1. GateCard — what action the human needs to take right now.
 *  2. RfcPanel — the artifact the gate is about (the doc being reviewed).
 *  3. IssueActivityTimeline — the agent's step-by-step log, below because it
 *     only matters when debugging or watching a live dispatch.
 *
 * Previous layout put the RFC at the very bottom, forcing users to scroll
 * past the full timeline to read the doc they just approved.
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
      <header className="space-y-1">
        <button
          type="button"
          onClick={() => navigate({ to: "/monitor" })}
          className="inline-flex items-center gap-1 text-xs text-soul-cyan/70 hover:text-ghost-white"
        >
          <ArrowLeft size={12} strokeWidth={2} />
          Back to monitor
        </button>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-semibold text-ghost-white">{key}</h1>
          <a
            href={`https://linear.app/issue/${key}`}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-xs text-arise-violet-bright hover:text-ghost-white"
          >
            Open in Linear
            <ExternalLink size={10} strokeWidth={2} />
          </a>
        </div>
        {ticket.data ? (
          <p className="text-sm text-soul-cyan/80">
            Orchestrator state: <code className="text-ghost-white/90">{ticket.data.state}</code>
            {ticket.data.branch_name ? (
              <>
                {" · branch "}
                <code className="text-ghost-white/90">{ticket.data.branch_name}</code>
              </>
            ) : null}
          </p>
        ) : null}
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
        <p className="text-sm text-soul-cyan/70">Inferring gate state…</p>
      ) : gate.isError ? (
        <p className="text-sm text-ember-red">
          {gate.error instanceof Error ? gate.error.message : "Gate fetch failed"}
        </p>
      ) : null}

      <RfcPanel issueKey={key} orchestratorState={ticket.data?.state ?? null} />

      <PlanPanel issueKey={key} orchestratorState={ticket.data?.state ?? null} />

      <IssueActivityTimeline issueKey={key} />
    </section>
  );
}
