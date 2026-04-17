import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/monitor")({
  component: Monitor,
});

function Monitor() {
  return (
    <section className="space-y-3">
      <h1 className="text-2xl font-semibold text-ghost-white">Agents Monitoring</h1>
      <p className="text-soul-cyan/90">
        Placeholder — ticket list, live event stream, and approval gates land in ENG-68.
      </p>
      <div className="rounded-md border border-shadow-purple/60 bg-void-800/70 p-5 text-sm text-soul-cyan">
        <span className="inline-flex items-center gap-2">
          <span className="h-2 w-2 animate-pulse rounded-full bg-mana-green shadow-[0_0_8px_#34d399]" />
          Orchestrator idle
        </span>
      </div>
    </section>
  );
}
