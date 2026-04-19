import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { DecisionsSidebar } from "~/components/DecisionsSidebar";
import { GateCard } from "~/components/GateCard";
import { RfcPanel } from "~/components/RfcPanel";
import { useGate } from "~/lib/gates";
import { useTicket } from "~/lib/issues";

/**
 * Per-issue detail view. One route, three panels:
 *   1. Gate state + lgtm / retry buttons   (ENG-95)
 *   2. Decisions sidebar                    (ENG-96)
 *   3. RFC render                           (ENG-98)
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

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]" data-layout="issue-detail-grid">
        <div className="flex flex-col gap-6">
          {gate.data ? (
            <GateCard
              issueKey={key}
              gate={gate.data}
              onRefresh={() => gate.refetch()}
              isRefreshing={gate.isFetching}
            />
          ) : gate.isLoading ? (
            <p className="text-sm text-soul-cyan/70">Inferring gate state…</p>
          ) : gate.isError ? (
            <p className="text-sm text-ember-red">
              {gate.error instanceof Error ? gate.error.message : "Gate fetch failed"}
            </p>
          ) : null}

          <RfcPanel issueKey={key} />
        </div>

        <DecisionsSidebar limit={10} />
      </div>
    </section>
  );
}
