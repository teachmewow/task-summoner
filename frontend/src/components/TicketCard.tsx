import { Link } from "@tanstack/react-router";
import type { TicketContext } from "~/lib/issues";
import { useReducedMotion } from "~/lib/motion";
import { PHASE_COLOR_VAR, type Phase, phaseFromOrchestratorState } from "~/lib/phases";
import { Glyph, PhaseRing, StreamPulse } from "./sigils";

/**
 * Monitor ticket cards — four visual variants matched to the ticket's
 * lifecycle bucket on the Monitor grid.
 *
 *  - ``GateTicketCard``    → awaiting human review  (ember glow)
 *  - ``RunningTicketCard`` → agent active           (phase-colored border, telemetry)
 *  - ``QueuedTicketCard``  → dispatched, not picked yet
 *  - ``DoneTicketCard``    → terminal (DONE / FAILED)
 *
 * All four share the same outer ``<Link>`` shell so the whole card routes
 * to ``/issues/$key``. The bulky visual bits (phase ring, live telemetry)
 * live only on the variants that actually need them, so queued/done stay
 * minimal.
 */

interface CardProps {
  ticket: TicketContext;
  /** Live-progress heuristic from ``useLiveProgress``, 0..1. */
  progress: number;
  /** Stagger index — used to offset the entrance animation per card. */
  index?: number;
}

/* ------------------------------------------------------------------ */
/* Data helpers                                                        */
/* ------------------------------------------------------------------ */

function getTitle(ticket: TicketContext): string {
  // We don't fetch Linear titles into TicketContext yet. ``gate_summary``
  // is a one-sentence human-readable summary the orchestrator stashes
  // — the closest thing we have to a title. Falls back to the key.
  const meta = ticket.metadata;
  const summary = meta?.gate_summary;
  if (typeof summary === "string" && summary.length > 0) return summary;
  return ticket.ticket_key;
}

function getTotalTurns(ticket: TicketContext): number | null {
  const history = (ticket as unknown as { cost_history?: { turns?: number }[] }).cost_history;
  if (!Array.isArray(history)) return null;
  return history.reduce((n, entry) => n + (entry?.turns ?? 0), 0);
}

function getLastProfile(ticket: TicketContext): string | null {
  const history = (ticket as unknown as { cost_history?: { profile?: string }[] }).cost_history;
  if (!Array.isArray(history) || history.length === 0) return null;
  return history[history.length - 1]?.profile ?? null;
}

function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const diff = Date.now() - then;
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function mapPhaseForRing(ticket: TicketContext): Phase | null {
  return phaseFromOrchestratorState(ticket.state);
}

function mapPhaseForBorder(state: string): "doc" | "plan" | "code" | null {
  const phase = phaseFromOrchestratorState(state);
  if (phase === "doc") return "doc";
  if (phase === "plan") return "plan";
  if (phase === "implement") return "code";
  return null;
}

function reviewLabel(state: string): string {
  if (state === "WAITING_DOC_REVIEW") return "Doc review";
  if (state === "WAITING_PLAN_REVIEW") return "Plan review";
  if (state === "WAITING_MR_REVIEW") return "Code review";
  return "Review";
}

function runningStateLabel(state: string): string {
  return state.toLowerCase().replace(/_/g, " ");
}

function cardAnimationStyle(index: number): React.CSSProperties {
  // Stagger entrance — each card delays its rune-in by a few frames.
  return { animationDelay: `${index * 60}ms` };
}

/* ------------------------------------------------------------------ */
/* GateTicketCard — awaiting your sigil                                */
/* ------------------------------------------------------------------ */

export function GateTicketCard({ ticket, progress, index = 0 }: CardProps) {
  const reducedMotion = useReducedMotion();
  const phase = mapPhaseForRing(ticket);
  const phaseKey = mapPhaseForBorder(ticket.state);
  return (
    <Link
      to="/issues/$key"
      params={{ key: ticket.ticket_key }}
      data-ticket-card="gate"
      data-ticket-state={ticket.state}
      className="surface-raised glow-ember anim-rune-in group relative block overflow-hidden p-4 transition hover:-translate-y-[2px]"
      style={{ ...cardAnimationStyle(index), borderColor: "rgba(255,138,91,0.28)" }}
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-2.5 -top-2.5"
        style={{ opacity: 0.55 }}
      >
        <PhaseRing size={64} phase={phase} progress={progress} active={!reducedMotion} />
      </div>

      <div className="mb-2 flex items-center gap-2">
        <span className="chip chip-ember">
          <span
            aria-hidden="true"
            style={{
              width: 5,
              height: 5,
              borderRadius: 999,
              background: "var(--color-ember)",
              boxShadow: "0 0 8px var(--color-ember)",
            }}
          />
          {reviewLabel(ticket.state)}
        </span>
        {ticket.retry_count > 0 ? (
          <span className="chip chip-blood">retry ×{ticket.retry_count}</span>
        ) : null}
      </div>

      <div className="font-mono text-xs tracking-wider text-arcane">{ticket.ticket_key}</div>
      <div
        className="mt-1 pr-[60px] text-[15px] font-medium leading-snug text-ghost"
        style={{ textWrap: "pretty" }}
      >
        {getTitle(ticket)}
      </div>

      <div className="mt-2.5 flex items-center gap-2.5 text-[11.5px] text-ghost-dim">
        <span className="truncate">{ticket.branch_name ?? "—"}</span>
        <span>·</span>
        <span>{formatRelativeTime(ticket.updated_at)}</span>
        <span>·</span>
        <span className="font-mono text-ghost">${ticket.total_cost_usd.toFixed(2)}</span>
      </div>

      <div className="mt-3 flex items-center justify-between">
        <span className="eyebrow text-[10px]" style={{ color: "var(--color-ember)" }}>
          Awaiting lgtm →
        </span>
        <Glyph kind="sigil" size={14} color="var(--color-ember)" />
      </div>

      {phaseKey === "doc" || phaseKey === "plan" || phaseKey === "code" ? null : null}
    </Link>
  );
}

/* ------------------------------------------------------------------ */
/* RunningTicketCard — in the ritual                                    */
/* ------------------------------------------------------------------ */

export function RunningTicketCard({ ticket, progress, index = 0 }: CardProps) {
  const reducedMotion = useReducedMotion();
  const phase = mapPhaseForRing(ticket);
  const phaseKey = mapPhaseForBorder(ticket.state);
  const phaseColor = phase ? PHASE_COLOR_VAR[phase] : "var(--color-arcane)";
  const borderTint =
    phaseKey === "doc"
      ? "rgba(245,183,105,0.30)"
      : phaseKey === "plan"
        ? "rgba(157,123,255,0.30)"
        : phaseKey === "code"
          ? "rgba(54,224,208,0.30)"
          : "var(--color-rune-line-strong)";
  const turns = getTotalTurns(ticket);
  const profile = getLastProfile(ticket);

  return (
    <Link
      to="/issues/$key"
      params={{ key: ticket.ticket_key }}
      data-ticket-card="running"
      data-ticket-state={ticket.state}
      className="surface-raised anim-rune-in group relative block overflow-hidden p-4 transition hover:-translate-y-[2px]"
      style={{ ...cardAnimationStyle(index), borderColor: borderTint }}
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-2 -top-2"
        style={{ opacity: 0.85 }}
      >
        <PhaseRing size={64} phase={phase} progress={progress} active={!reducedMotion} />
      </div>

      <div className="mb-2 flex items-center gap-2">
        <span className={`chip ${phaseKey ? `chip-${phaseKey}` : ""}`}>
          <StreamPulse color={phaseColor} />
          {runningStateLabel(ticket.state)}
        </span>
        {profile ? <span className="chip">{profile}</span> : null}
      </div>

      <div className="font-mono text-xs tracking-wider" style={{ color: phaseColor }}>
        {ticket.ticket_key}
      </div>
      <div
        className="mt-1 pr-[60px] text-[15px] font-medium leading-snug text-ghost"
        style={{ textWrap: "pretty" }}
      >
        {getTitle(ticket)}
      </div>

      <div className="mt-3 flex items-center gap-3 font-mono text-[11px]">
        {turns != null ? <TeleBlock icon="◉" label="turns" value={String(turns)} /> : null}
        <TeleBlock icon="◈" label="cost" value={`$${ticket.total_cost_usd.toFixed(2)}`} />
        <TeleBlock icon="◐" label="turn" value={`${Math.round(progress * 100)}%`} />
      </div>

      <div className="mt-2.5 flex items-center gap-2.5 text-[11.5px] text-ghost-dim">
        <span className="truncate">{ticket.branch_name ?? "—"}</span>
        <span>·</span>
        <span>{formatRelativeTime(ticket.updated_at)}</span>
      </div>
    </Link>
  );
}

function TeleBlock({ icon, label, value }: { icon: string; label: string; value: string }) {
  return (
    <div className="flex flex-col leading-[1.2]">
      <span className="text-[9px] uppercase tracking-[0.2em] text-ghost-dim">
        {icon} {label}
      </span>
      <span className="text-ghost">{value}</span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* QueuedTicketCard — not yet summoned                                  */
/* ------------------------------------------------------------------ */

export function QueuedTicketCard({ ticket, index = 0 }: Omit<CardProps, "progress">) {
  return (
    <Link
      to="/issues/$key"
      params={{ key: ticket.ticket_key }}
      data-ticket-card="queued"
      data-ticket-state={ticket.state}
      className="surface anim-rune-in block p-3.5 opacity-75 transition hover:opacity-100"
      style={cardAnimationStyle(index)}
    >
      <div className="mb-1.5 flex items-center gap-2">
        <span className="chip chip-idle">queued</span>
        <span className="font-mono text-[11px] text-ghost-dim">{ticket.ticket_key}</span>
      </div>
      <div className="text-[13px] text-ghost">{getTitle(ticket)}</div>
    </Link>
  );
}

/* ------------------------------------------------------------------ */
/* DoneTicketCard — bound                                               */
/* ------------------------------------------------------------------ */

export function DoneTicketCard({ ticket, index = 0 }: Omit<CardProps, "progress">) {
  const turns = getTotalTurns(ticket);
  const isFailed = ticket.state === "FAILED";
  return (
    <Link
      to="/issues/$key"
      params={{ key: ticket.ticket_key }}
      data-ticket-card="done"
      data-ticket-state={ticket.state}
      className="surface anim-rune-in block p-3.5 transition hover:-translate-y-[1px]"
      style={cardAnimationStyle(index)}
    >
      <div className="mb-1.5 flex items-center gap-2">
        <span className={`chip ${isFailed ? "chip-blood" : "chip-done"}`}>
          {isFailed ? null : (
            <span
              aria-hidden="true"
              style={{
                width: 5,
                height: 5,
                borderRadius: 999,
                background: "var(--color-phase-done)",
              }}
            />
          )}
          {isFailed ? "failed" : "merged"}
        </span>
        <span className="font-mono text-[11px] text-ghost-dim">{ticket.ticket_key}</span>
      </div>
      <div className="text-[13px] text-ghost">{getTitle(ticket)}</div>
      <div className="mt-1.5 font-mono text-[11px] text-ghost-dim">
        ${ticket.total_cost_usd.toFixed(2)}
        {turns != null ? ` · ${turns} turns` : ""} · {formatRelativeTime(ticket.updated_at)}
      </div>
    </Link>
  );
}

/* ------------------------------------------------------------------ */
/* Dispatcher (back-compat)                                             */
/* ------------------------------------------------------------------ */

/**
 * Pick the right variant by bucket. Kept for callers (and tests) that
 * just want to pass a ticket without branching themselves.
 */
export function TicketCard({ ticket, progress, index = 0 }: CardProps) {
  const state = ticket.state;
  if (state.startsWith("WAITING_")) {
    return <GateTicketCard ticket={ticket} progress={progress} index={index} />;
  }
  if (state === "QUEUED") {
    return <QueuedTicketCard ticket={ticket} index={index} />;
  }
  if (state === "DONE" || state === "FAILED") {
    return <DoneTicketCard ticket={ticket} index={index} />;
  }
  return <RunningTicketCard ticket={ticket} progress={progress} index={index} />;
}
