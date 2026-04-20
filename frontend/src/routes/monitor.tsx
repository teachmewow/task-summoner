import { createFileRoute } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { useMemo } from "react";
import { OrchestratorStatusBlock } from "~/components/OrchestratorStatusBlock";
import {
  DoneTicketCard,
  GateTicketCard,
  QueuedTicketCard,
  RunningTicketCard,
} from "~/components/TicketCard";
import type { TicketContext } from "~/lib/issues";
import { useTickets } from "~/lib/issues";
import { useLiveProgress } from "~/lib/useLiveProgress";

/**
 * Monitor route — the Arcane Command Bridge hero + 4 responsive card
 * grids, one per lifecycle bucket. Matches the Claude Design bundle's
 * ``MonitorView``:
 *
 *  1. Awaiting your sigil  — gates calling for judgment  (ember)
 *  2. In the ritual        — agents active               (arcane)
 *  3. Not yet summoned     — queue                       (idle)
 *  4. Bound                — completed                   (done)
 *
 * Each section renders an eyebrow + title + sub + a coloured dot; empty
 * buckets hide entirely so the page doesn't bloat with placeholder copy.
 */

export const Route = createFileRoute("/monitor")({
  component: Monitor,
});

const WAITING_STATES = new Set(["WAITING_DOC_REVIEW", "WAITING_PLAN_REVIEW", "WAITING_MR_REVIEW"]);
const TERMINAL_STATES = new Set(["DONE", "FAILED"]);

interface Buckets {
  waiting: TicketContext[];
  running: TicketContext[];
  queued: TicketContext[];
  done: TicketContext[];
}

function bucketTickets(tickets: TicketContext[]): Buckets {
  const waiting: TicketContext[] = [];
  const running: TicketContext[] = [];
  const queued: TicketContext[] = [];
  const done: TicketContext[] = [];
  for (const t of tickets) {
    if (WAITING_STATES.has(t.state)) waiting.push(t);
    else if (TERMINAL_STATES.has(t.state)) done.push(t);
    else if (t.state === "QUEUED") queued.push(t);
    else running.push(t);
  }
  const byUpdated = (a: TicketContext, b: TicketContext) =>
    (b.updated_at ?? "").localeCompare(a.updated_at ?? "");
  return {
    waiting: waiting.sort(byUpdated),
    running: running.sort(byUpdated),
    queued: queued.sort(byUpdated),
    done: done.sort(byUpdated),
  };
}

function Monitor() {
  const { data, isLoading, isError, error } = useTickets();
  const progressByKey = useLiveProgress(data);
  const buckets = useMemo(() => bucketTickets(data ?? []), [data]);
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
      <OrchestratorStatusBlock
        running={buckets.running.length}
        waiting={buckets.waiting.length}
        queued={buckets.queued.length}
      />

      {total === 0 ? (
        <div className="surface-raised p-8 text-center">
          <p className="text-sm text-ghost">No tickets tracked yet.</p>
          <p className="mt-1 text-xs text-ghost-dim">
            Label a Linear issue with your watch label (e.g. <code>task-summoner</code>) and the
            orchestrator will pick it up.
          </p>
        </div>
      ) : null}

      {buckets.waiting.length > 0 ? (
        <Section
          eyebrow="Awaiting your sigil"
          title="Gates calling for judgment"
          sub={`${buckets.waiting.length} summoning${buckets.waiting.length > 1 ? "s" : ""} parked at a review gate.`}
          accent="ember"
        >
          <CardGrid minColWidth={340}>
            {buckets.waiting.map((t, i) => (
              <GateTicketCard
                key={t.ticket_key}
                ticket={t}
                progress={progressByKey[t.ticket_key] ?? 0}
                index={i}
              />
            ))}
          </CardGrid>
        </Section>
      ) : null}

      {buckets.running.length > 0 ? (
        <Section
          eyebrow="In the ritual"
          title="Agents active"
          sub={`${buckets.running.length} subprocess${buckets.running.length > 1 ? "es" : ""} running in parallel.`}
          accent="arcane"
        >
          <CardGrid minColWidth={340}>
            {buckets.running.map((t, i) => (
              <RunningTicketCard
                key={t.ticket_key}
                ticket={t}
                progress={progressByKey[t.ticket_key] ?? 0}
                index={i}
              />
            ))}
          </CardGrid>
        </Section>
      ) : null}

      {buckets.queued.length > 0 ? (
        <Section eyebrow="Not yet summoned" title="Queue" accent="idle">
          <CardGrid minColWidth={320}>
            {buckets.queued.map((t, i) => (
              <QueuedTicketCard key={t.ticket_key} ticket={t} index={i} />
            ))}
          </CardGrid>
        </Section>
      ) : null}

      {buckets.done.length > 0 ? (
        <Section eyebrow="Bound" title="Completed" accent="done">
          <CardGrid minColWidth={320}>
            {buckets.done.map((t, i) => (
              <DoneTicketCard key={t.ticket_key} ticket={t} index={i} />
            ))}
          </CardGrid>
        </Section>
      ) : null}
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Section header + responsive card grid                               */
/* ------------------------------------------------------------------ */

type Accent = "ember" | "arcane" | "idle" | "done";

const ACCENT_COLOR: Record<Accent, string> = {
  ember: "var(--color-ember)",
  arcane: "var(--color-arcane)",
  idle: "var(--color-ghost-dimmer)",
  done: "var(--color-phase-done)",
};

function Section({
  eyebrow,
  title,
  sub,
  accent,
  children,
}: {
  eyebrow: string;
  title: string;
  sub?: string;
  accent: Accent;
  children: ReactNode;
}) {
  const dot = ACCENT_COLOR[accent];
  return (
    <section className="anim-rune-in flex flex-col gap-3.5">
      <header className="flex flex-wrap items-baseline gap-3.5">
        <div className="flex items-center gap-2.5">
          <span
            aria-hidden="true"
            style={{
              width: 6,
              height: 6,
              borderRadius: 999,
              background: dot,
              boxShadow: `0 0 10px ${dot}`,
            }}
          />
          <span className="eyebrow">{eyebrow}</span>
        </div>
        <h2 className="m-0 text-xl font-semibold tracking-tight text-ghost">{title}</h2>
        {sub ? <p className="m-0 text-[13px] text-ghost-dim">{sub}</p> : null}
      </header>
      {children}
    </section>
  );
}

function CardGrid({ minColWidth, children }: { minColWidth: number; children: ReactNode }) {
  return (
    <div
      className="grid gap-3.5"
      style={{
        gridTemplateColumns: `repeat(auto-fill, minmax(${minColWidth}px, 1fr))`,
      }}
    >
      {children}
    </div>
  );
}
