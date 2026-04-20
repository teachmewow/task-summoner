import { createFileRoute } from "@tanstack/react-router";
import { useMemo } from "react";
import { OrchestratorStatusBlock } from "~/components/OrchestratorStatusBlock";
import { TicketCard } from "~/components/TicketCard";
import type { TicketContext } from "~/lib/issues";
import { useTickets } from "~/lib/issues";
import { useLiveProgress } from "~/lib/useLiveProgress";

/**
 * Monitor route (REVAMP M2 / ENG-176).
 *
 * Four sections in descending urgency:
 *   1. Gates waiting   — awaiting human review
 *   2. Active          — agent running right now
 *   3. Queued          — dispatched but not picked up yet
 *   4. Done            — terminal (DONE / FAILED)
 *
 * Each section renders the new ``TicketCard`` (ENG-175) sorted by
 * ``updated_at`` descending so the freshest activity lands on top.
 *
 * ``GatesWaitingPanel`` used to live as a separate sidebar; its role is
 * absorbed into section 1 here and the component is deleted.
 */

export const Route = createFileRoute("/monitor")({
  component: Monitor,
});

const WAITING_STATES = new Set(["WAITING_DOC_REVIEW", "WAITING_PLAN_REVIEW", "WAITING_MR_REVIEW"]);
const TERMINAL_STATES = new Set(["DONE", "FAILED"]);

type Section = { id: string; label: string; emptyHint: string; tickets: TicketContext[] };

function bucketTickets(tickets: TicketContext[]): Section[] {
  const waiting: TicketContext[] = [];
  const active: TicketContext[] = [];
  const queued: TicketContext[] = [];
  const done: TicketContext[] = [];
  for (const t of tickets) {
    if (WAITING_STATES.has(t.state)) waiting.push(t);
    else if (TERMINAL_STATES.has(t.state)) done.push(t);
    else if (t.state === "QUEUED") queued.push(t);
    else active.push(t);
  }
  const byUpdated = (a: TicketContext, b: TicketContext) =>
    (b.updated_at ?? "").localeCompare(a.updated_at ?? "");
  return [
    {
      id: "gates-waiting",
      label: "Gates waiting",
      emptyHint: "Nothing parked for human review right now.",
      tickets: waiting.sort(byUpdated),
    },
    {
      id: "active",
      label: "Active",
      emptyHint: "No agent run in progress.",
      tickets: active.sort(byUpdated),
    },
    {
      id: "queued",
      label: "Queued",
      emptyHint: "No tickets queued for dispatch.",
      tickets: queued.sort(byUpdated),
    },
    {
      id: "done",
      label: "Done",
      emptyHint: "Nothing finished yet this session.",
      tickets: done.sort(byUpdated),
    },
  ];
}

function Monitor() {
  const { data, isLoading, isError, error } = useTickets();
  const progressByKey = useLiveProgress(data);

  const sections = useMemo(() => bucketTickets(data ?? []), [data]);
  // ``bucketTickets`` always returns the 4 section shells in fixed order;
  // the guards keep TypeScript strict-index-happy.
  const runningCount = (sections[0]?.tickets.length ?? 0) + (sections[1]?.tickets.length ?? 0);
  const total = data?.length ?? 0;

  if (isLoading) {
    return <p className="text-sm text-ghost-dim">Loading tickets…</p>;
  }
  if (isError) {
    return (
      <p className="text-sm text-blood">
        {error instanceof Error ? error.message : "Failed to load tickets"}
      </p>
    );
  }

  return (
    <section className="flex flex-col gap-6" data-route="monitor">
      <OrchestratorStatusBlock running={runningCount} total={total} />

      {total === 0 ? (
        <div className="rounded-xl border border-rune-line bg-obsidian-raised p-8 text-center">
          <p className="text-sm text-ghost">No tickets tracked yet.</p>
          <p className="mt-1 text-xs text-ghost-dim">
            Label a Linear issue with your watch label (e.g. <code>task-summoner</code>) and the
            orchestrator will pick it up.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-5">
          {sections.map((section) => (
            <TicketSection key={section.id} section={section} progressByKey={progressByKey} />
          ))}
        </div>
      )}
    </section>
  );
}

interface TicketSectionProps {
  section: Section;
  progressByKey: Record<string, number>;
}

function TicketSection({ section, progressByKey }: TicketSectionProps) {
  const { label, emptyHint, tickets } = section;
  return (
    <section data-monitor-section={section.id} className="flex flex-col gap-2">
      <header className="flex items-center justify-between">
        <h2 className="font-mono text-[11px] uppercase tracking-wider text-ghost-dim">{label}</h2>
        <span className="font-mono text-[10px] text-ghost-dimmer">
          {tickets.length} {tickets.length === 1 ? "ticket" : "tickets"}
        </span>
      </header>
      {tickets.length === 0 ? (
        <p className="rounded-lg border border-rune-line bg-obsidian-raised/60 px-4 py-3 text-xs text-ghost-dimmer">
          {emptyHint}
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {tickets.map((ticket) => (
            <li key={ticket.ticket_key}>
              <TicketCard ticket={ticket} progress={progressByKey[ticket.ticket_key] ?? 0} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
