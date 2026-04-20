import { Link, createFileRoute } from "@tanstack/react-router";
import { ArrowUpRight } from "lucide-react";
import { GatesWaitingPanel } from "~/components/GatesWaitingPanel";
import { useTickets } from "~/lib/issues";

export const Route = createFileRoute("/monitor")({
  component: Monitor,
});

function Monitor() {
  const { data, isLoading, isError, error } = useTickets();

  return (
    <section className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-ghost-white">Agents Monitoring</h1>
        <p className="text-soul-cyan/90">
          Pick an issue to see its gate state, or jump straight into one waiting for review.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-3">
          <div className="rounded-md border border-shadow-purple/60 bg-void-800/70 p-5 text-sm text-soul-cyan">
            <span className="inline-flex items-center gap-2">
              <span className="h-2 w-2 animate-pulse rounded-full bg-mana-green shadow-[0_0_8px_#34d399]" />
              Orchestrator running
            </span>
          </div>

          {isLoading ? (
            <p className="text-sm text-soul-cyan/70">Loading tickets…</p>
          ) : isError ? (
            <p className="text-sm text-ember-red">
              {error instanceof Error ? error.message : "Failed to load tickets"}
            </p>
          ) : !data || data.length === 0 ? (
            <div className="rounded-md border border-shadow-purple/60 bg-void-800/70 p-5 text-sm text-soul-cyan/80">
              No tickets are being tracked yet. Label a Linear issue with your watch label and the
              orchestrator will pick it up.
            </div>
          ) : (
            <ul className="flex flex-col gap-2">
              {data.map((ctx) => (
                <li key={ctx.ticket_key}>
                  <Link
                    to="/issues/$key"
                    params={{ key: ctx.ticket_key }}
                    className="flex items-center justify-between gap-3 rounded-md border border-shadow-purple/60 bg-void-800/70 p-4 transition hover:border-arise-violet/50"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-ghost-white">
                        {ctx.ticket_key}
                      </p>
                      <p className="truncate text-xs text-soul-cyan/70">
                        {ctx.state}
                        {ctx.branch_name ? (
                          <>
                            {" · "}
                            <code className="text-ghost-white/80">{ctx.branch_name}</code>
                          </>
                        ) : null}
                      </p>
                    </div>
                    <ArrowUpRight size={14} strokeWidth={2} className="text-arise-violet" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        <GatesWaitingPanel />
      </div>
    </section>
  );
}
