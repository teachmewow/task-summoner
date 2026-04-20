/**
 * Phase mapping utilities for REVAMP M2 / M3.
 *
 * The task-summoner FSM has 12 states (see ``backend/src/task_summoner/
 * models/enums.py``) but the UI clusters them into 4 **phases** —
 * doc / plan / implement / merged — each with its own phase color. The
 * mapping is pure data: no heuristics, no inference from PR state, no
 * Linear status peeking.
 *
 * Used by:
 *  - ``TicketCard`` (phase ring color)
 *  - ``PhaseStrip`` (4-glyph progress rail on the Issue Detail page)
 *  - ``StepGroupBox`` (per-step rune in the Activity Timeline)
 *
 * Keeping the mapping in one file means all three consumers agree on
 * which state belongs to which phase — no drift.
 */

export type Phase = "doc" | "plan" | "implement" | "merged";

export const PHASES: readonly Phase[] = ["doc", "plan", "implement", "merged"] as const;

/** CSS custom-property name that paints a phase-colored surface. */
export const PHASE_COLOR_VAR: Record<Phase, string> = {
  doc: "var(--color-phase-doc)",
  plan: "var(--color-phase-plan)",
  implement: "var(--color-phase-code)",
  merged: "var(--color-phase-done)",
};

/** Tailwind utility token for the same phase color (for ``bg-*`` / ``text-*``). */
export const PHASE_TAILWIND_TOKEN: Record<Phase, string> = {
  doc: "phase-doc",
  plan: "phase-plan",
  implement: "phase-code",
  merged: "phase-done",
};

/**
 * Map an orchestrator FSM state to its UI phase.
 *
 * - Doc-path states (including the classifier, creation, and doc review)
 *   all belong to "doc".
 * - Planning + plan review → "plan".
 * - Implementing + code review + fixing → "implement".
 * - DONE → "merged".
 * - FAILED → ``null``. Callers decide whether to render the last-known
 *   phase or a distinct failure style.
 * - Any unknown state (schema drift / old ``state.json``) falls back to
 *   ``null`` so the UI shows a neutral marker rather than asserting.
 */
export function phaseFromOrchestratorState(state: string | null | undefined): Phase | null {
  if (!state) return null;
  switch (state) {
    case "QUEUED":
    case "CHECKING_DOC":
    case "CREATING_DOC":
    case "WAITING_DOC_REVIEW":
    case "IMPROVING_DOC":
      return "doc";
    case "PLANNING":
    case "WAITING_PLAN_REVIEW":
      return "plan";
    case "IMPLEMENTING":
    case "WAITING_MR_REVIEW":
    case "FIXING_MR":
      return "implement";
    case "DONE":
      return "merged";
    default:
      return null;
  }
}

/** Human-friendly label used next to the phase glyph. */
export const PHASE_LABEL: Record<Phase, string> = {
  doc: "Design doc",
  plan: "Plan",
  implement: "Implement",
  merged: "Merged",
};
