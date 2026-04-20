import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { GateCard } from "~/components/GateCard";
import { IssueActivityTimeline } from "~/components/IssueActivityTimeline";
import { useGate } from "~/lib/gates";
import { useTicket } from "~/lib/issues";

/**
 * Per-issue detail view.
 *
 * Order is deliberately "decision → agent trace":
 *
 *  1. GateCard — what action the human needs to take right now. The gate
 *     surfaces ``Preview RFC`` / ``Preview Plan`` buttons that open a modal
 *     with the relevant artifact, so the page itself stays tight.
 *  2. IssueActivityTimeline — the agent's step-by-step log, including the
 *     collapsed step groups (``✓ Creating doc · N turns · $X.XX``) that let
 *     the user re-read any completed phase.
 *
 * The standalone ``RfcPanel`` / ``PlanPanel`` sections that used to live
 * between gate and timeline were deleted: the Preview modal covers the
 * review case, and expanding the relevant timeline step covers the
 * after-the-fact re-read case — two places to read the same doc was
 * duplicate surface.
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

      <IssueActivityTimeline issueKey={key} />
    </section>
  );
}
