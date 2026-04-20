import { Link } from "@tanstack/react-router";
import { ArrowUpRight, RefreshCw } from "lucide-react";
import type { TicketContext } from "~/lib/issues";
import { MOTION_CLASSES } from "~/lib/motion";
import { PHASE_COLOR_VAR, PHASE_LABEL, phaseFromOrchestratorState } from "~/lib/phases";
import { isProgressActive } from "~/lib/progress";

/**
 * Monitor-page ticket card (REVAMP M2, ENG-175).
 *
 * One card per ticket. Shape:
 *
 *   ┌────────────────────────────────────────────────────────┐
 *   │ (phase ring)  ENG-123  · in doc review     →           │
 *   │               <ticket title>                           │
 *   │               branch name · retry 2/3                  │
 *   │               ████████░░░░░░░░  ($0.43 · 51k tokens)   │
 *   └────────────────────────────────────────────────────────┘
 *
 * Phase ring color is derived client-side from ``orchestrator_state``
 * via ``phaseFromOrchestratorState``. Progress bar only renders for
 * in-flight tickets. Retry-count chip only renders when > 0.
 *
 * The whole card is a ``<Link>`` to ``/issues/$key``.
 */
interface Props {
  ticket: TicketContext;
  /** Live-progress value from ``useLiveProgress``, 0–1. */
  progress: number;
}

export function TicketCard({ ticket, progress }: Props) {
  const phase = phaseFromOrchestratorState(ticket.state);
  const isFailed = ticket.state === "FAILED";
  const isTerminal = ticket.state === "DONE" || isFailed;
  const showProgress = isProgressActive(ticket.state);
  const stateLabel = formatStateLabel(ticket.state);

  return (
    <Link
      to="/issues/$key"
      params={{ key: ticket.ticket_key }}
      data-ticket-card
      data-ticket-state={ticket.state}
      className={`group flex items-center gap-4 rounded-xl border border-rune-line bg-obsidian-raised p-4 transition hover:border-rune-line-strong hover:-translate-y-[1px] ${MOTION_CLASSES.runeIn}`}
    >
      <PhaseRing phase={phase} isFailed={isFailed} isTerminal={isTerminal} />

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs font-semibold tracking-wider text-arcane">
            {ticket.ticket_key}
          </span>
          <span className="text-[10px] uppercase tracking-wider text-ghost-dimmer">·</span>
          <span className="text-[11px] uppercase tracking-wider text-ghost-dim">{stateLabel}</span>
          {ticket.retry_count > 0 ? (
            <span className="ml-1 inline-flex items-center gap-1 rounded-full border border-ember/50 bg-ember/10 px-1.5 py-[1px] text-[10px] font-medium text-ember">
              <RefreshCw size={9} strokeWidth={2.5} />
              retry {ticket.retry_count}
            </span>
          ) : null}
        </div>
        {ticket.branch_name ? (
          <p className="mt-0.5 truncate font-mono text-[11px] text-ghost-dimmer">
            {ticket.branch_name}
          </p>
        ) : null}

        {showProgress ? (
          <div className="mt-2 flex items-center gap-2">
            <div className="relative h-1 flex-1 overflow-hidden rounded-full bg-vault">
              <div
                className="absolute inset-y-0 left-0 rounded-full"
                style={{
                  width: `${Math.round(progress * 100)}%`,
                  background: phase ? PHASE_COLOR_VAR[phase] : "var(--color-arcane)",
                  transition: "width 500ms ease-out",
                }}
              />
            </div>
            <span className="font-mono text-[10px] text-ghost-dimmer">
              ${ticket.total_cost_usd.toFixed(2)}
            </span>
          </div>
        ) : (
          <p className="mt-1 font-mono text-[10px] text-ghost-dimmer">
            ${ticket.total_cost_usd.toFixed(2)} lifetime
          </p>
        )}
      </div>

      <ArrowUpRight
        size={14}
        strokeWidth={2}
        className="shrink-0 text-ghost-dimmer transition group-hover:text-arcane"
      />
    </Link>
  );
}

/** Small label replacing the raw FSM constant (UPPER_SNAKE is ugly in the chip row). */
function formatStateLabel(state: string): string {
  if (state === "WAITING_DOC_REVIEW") return "in doc review";
  if (state === "WAITING_PLAN_REVIEW") return "in plan review";
  if (state === "WAITING_MR_REVIEW") return "in code review";
  if (state === "CREATING_DOC") return "drafting doc";
  if (state === "IMPROVING_DOC") return "revising doc";
  if (state === "PLANNING") return "planning";
  if (state === "IMPLEMENTING") return "implementing";
  if (state === "FIXING_MR") return "fixing PR";
  if (state === "QUEUED") return "queued";
  if (state === "CHECKING_DOC") return "triage";
  if (state === "DONE") return "done";
  if (state === "FAILED") return "failed";
  return state.toLowerCase().replace(/_/g, " ");
}

interface PhaseRingProps {
  phase: ReturnType<typeof phaseFromOrchestratorState>;
  isFailed: boolean;
  isTerminal: boolean;
}

function PhaseRing({ phase, isFailed, isTerminal }: PhaseRingProps) {
  const size = 38;
  const half = size / 2;
  const color = isFailed
    ? "var(--color-blood)"
    : phase
      ? PHASE_COLOR_VAR[phase]
      : "var(--color-ghost-dimmer)";
  const label = isFailed ? "FAILED" : phase ? PHASE_LABEL[phase] : "";
  return (
    <div className="relative shrink-0" title={label}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        aria-hidden="true"
        className={!isTerminal ? MOTION_CLASSES.phaseRing : undefined}
        style={{ transformOrigin: "center" }}
      >
        <circle
          cx={half}
          cy={half}
          r={half - 3}
          fill="none"
          stroke="var(--color-rune-line-strong)"
          strokeWidth={1}
        />
        <circle
          cx={half}
          cy={half}
          r={half - 3}
          fill="none"
          stroke={color}
          strokeWidth={2}
          strokeDasharray="8 4"
          opacity={isTerminal ? 0.9 : 0.8}
        />
        <circle cx={half} cy={half} r={4} fill={color} />
      </svg>
    </div>
  );
}
