import { FileText, GitPullRequest, Hammer, ScrollText } from "lucide-react";
import type { ComponentType } from "react";
import { MOTION_CLASSES } from "~/lib/motion";
import {
  PHASES,
  PHASE_COLOR_VAR,
  PHASE_LABEL,
  type Phase,
  phaseFromOrchestratorState,
} from "~/lib/phases";

/**
 * 4-glyph phase progression rail (REVAMP M3 / ENG-178).
 *
 * Horizontal strip showing the mission's journey through the FSM:
 * ``doc → plan → implement → merged``. Each glyph has one of three
 * states:
 *
 *  - ``done``     — phase already passed, filled with phase color.
 *  - ``active``   — current phase; filled + pulsing ring.
 *  - ``upcoming`` — not yet reached; dim outline, no fill.
 *
 * Ley-lines between glyphs brighten as we advance — traversed edges
 * use ``--color-arcane``, untraversed edges use ``--color-rune-line``.
 *
 * Phase derivation lives in ``~/lib/phases`` so PhaseStrip,
 * TicketCard's phase ring, and M3's ``StepGroupBox`` rune glyphs all
 * read from the same mapping — no drift.
 */

interface Props {
  /** FSM state from ``TicketContext.state`` — if null, first phase is active. */
  orchestratorState: string | null | undefined;
}

const GLYPH_BY_PHASE: Record<Phase, ComponentType<{ size: number; strokeWidth?: number }>> = {
  doc: FileText,
  plan: ScrollText,
  implement: Hammer,
  merged: GitPullRequest,
};

type Status = "done" | "active" | "upcoming";

function statusFor(currentIndex: number, glyphIndex: number): Status {
  if (glyphIndex < currentIndex) return "done";
  if (glyphIndex === currentIndex) return "active";
  return "upcoming";
}

export function PhaseStrip({ orchestratorState }: Props) {
  const currentPhase = phaseFromOrchestratorState(orchestratorState);
  const isFailed = orchestratorState === "FAILED";
  // When FAILED, there's no current phase — render every glyph as
  // upcoming (dim) except the first, which is marked as failed.
  // The mission brief accepted this trade-off: showing "the phase it
  // died on" requires cost_history peeking which we've deferred.
  const currentIndex = currentPhase ? PHASES.indexOf(currentPhase) : -1;

  return (
    <div
      data-phase-strip
      aria-label={
        currentPhase ? `Currently in ${PHASE_LABEL[currentPhase]} phase` : "Phase not started"
      }
      className="flex items-center gap-1"
    >
      {PHASES.map((phase, idx) => {
        const status = isFailed ? "upcoming" : statusFor(currentIndex, idx);
        const isLast = idx === PHASES.length - 1;
        return (
          <div key={phase} className="flex min-w-0 flex-1 items-center gap-1 last:flex-none">
            <PhaseGlyph phase={phase} status={status} />
            {!isLast && <LeyLine traversed={status === "done"} />}
          </div>
        );
      })}
    </div>
  );
}

interface PhaseGlyphProps {
  phase: Phase;
  status: Status;
}

function PhaseGlyph({ phase, status }: PhaseGlyphProps) {
  const Glyph = GLYPH_BY_PHASE[phase];
  const color = PHASE_COLOR_VAR[phase];
  const isActive = status === "active";
  const isDone = status === "done";

  return (
    <div
      data-phase={phase}
      data-phase-status={status}
      title={`${PHASE_LABEL[phase]} · ${status}`}
      className="relative flex flex-col items-center gap-1.5"
    >
      <div
        className={[
          "relative flex h-10 w-10 items-center justify-center rounded-full border-2 transition",
          isActive ? MOTION_CLASSES.particleSpark : "",
        ].join(" ")}
        style={{
          borderColor: isActive || isDone ? color : "var(--color-rune-line-strong)",
          background: isDone ? `${color}20` : "transparent",
          boxShadow: isActive ? `0 0 14px ${color}55` : "none",
        }}
      >
        <Glyph size={16} strokeWidth={2} />
      </div>
      <span
        className="font-mono text-[9px] uppercase tracking-wider"
        style={{ color: isActive || isDone ? color : "var(--color-ghost-dimmer)" }}
      >
        {PHASE_LABEL[phase]}
      </span>
    </div>
  );
}

interface LeyLineProps {
  traversed: boolean;
}

function LeyLine({ traversed }: LeyLineProps) {
  return (
    <div
      aria-hidden="true"
      className="h-[2px] flex-1"
      style={{
        background: traversed ? "var(--color-arcane)" : "var(--color-rune-line-strong)",
        boxShadow: traversed ? "0 0 6px var(--arcane-glow)" : "none",
        opacity: traversed ? 0.9 : 0.6,
      }}
    />
  );
}
