/**
 * Client-side progress heuristic for the Monitor telemetry ticker
 * (REVAMP M2, ENG-173 + ENG-177).
 *
 * The orchestrator doesn't emit a per-tick "progress: 0-1" field — that
 * would require plumbing new events through the SSE stream and the state
 * handler contracts. Instead we fake a believable bar client-side: each
 * ticker tick nudges an in-flight ticket's progress up by a small random
 * increment, capped at ``MAX_PROGRESS``. The cap is the honesty knob —
 * only the real FSM transition to DONE can push the bar to 100 %.
 *
 * Starting points by state reflect what the user actually wants to see:
 * a freshly-claimed QUEUED ticket shows empty, a state mid-execution
 * picks up at ~10 %, and a WAITING_*_REVIEW ticket is basically "done
 * except for your click" so it sits at 95 %. Terminal states pin to 1.
 *
 * No server field, no backend change, no test theatrics. The rendered
 * number is a vibe indicator, not a fact.
 */

/** The bar never reaches 100 % from the heuristic alone — DONE does that. */
export const MAX_PROGRESS = 0.98;

/** Per-tick nudge range. Matches the pacing of the Claude Design prototype. */
const TICK_MAX_DELTA = 0.01;

/**
 * Advance one ticket's progress by one tick.
 *
 * Pure function — callers own the value across renders. Random but bounded
 * so consecutive calls trend upward without visible jumps.
 */
export function advanceProgress(current: number): number {
  if (current >= MAX_PROGRESS) return MAX_PROGRESS;
  const next = current + Math.random() * TICK_MAX_DELTA;
  return Math.min(MAX_PROGRESS, next);
}

/**
 * Starting progress for a ticket we've never ticked before.
 *
 * The ticker seeds each ticket with this value on first observation, then
 * ``advanceProgress`` takes over.
 */
export function initialProgress(orchestratorState: string | null | undefined): number {
  if (!orchestratorState) return 0;
  if (orchestratorState === "DONE" || orchestratorState === "FAILED") return 1;
  if (orchestratorState === "QUEUED") return 0;
  // WAITING_*_REVIEW tickets are parked for human review — the work
  // under the hood already finished, so show the bar basically full.
  if (orchestratorState.startsWith("WAITING_")) return 0.95;
  // Everything else (CHECKING_DOC, CREATING_DOC, PLANNING, IMPLEMENTING,
  // IMPROVING_DOC, FIXING_MR) is an in-flight agent run — start ~10 %.
  return 0.1;
}

/**
 * True iff the state should keep ticking. The ticker checks this before
 * advancing so DONE/FAILED/WAITING_* tickets don't waste work.
 */
export function isProgressActive(orchestratorState: string | null | undefined): boolean {
  if (!orchestratorState) return false;
  if (orchestratorState === "DONE" || orchestratorState === "FAILED") return false;
  if (orchestratorState === "QUEUED") return false;
  if (orchestratorState.startsWith("WAITING_")) return false;
  return true;
}
