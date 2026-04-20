import { useEffect, useRef, useState } from "react";
import type { TicketContext } from "./issues";
import { useReducedMotion } from "./motion";
import { advanceProgress, initialProgress, isProgressActive } from "./progress";

/**
 * Per-ticket live progress map + ticker, scoped to a single mount.
 *
 * Product intent (REVAMP M2 / ENG-177): the Monitor page shows a small
 * progress bar on every in-flight ticket. The backend doesn't emit
 * per-tick progress, so this hook invents one client-side — seeding
 * each ticket from ``initialProgress`` on first sight, then advancing
 * via a single ``setInterval`` at 1.5 s. Terminal + queued + waiting
 * tickets don't consume ticker budget; they're pinned to their initial
 * value.
 *
 * Motion gate: when the user opted into reduced motion, the interval
 * never starts — the bar renders its initial value and stays there.
 *
 * One interval per mount (the whole Monitor), not one per card. Caller
 * passes the full ticket list and reads back a ``progressByKey`` map.
 */
const TICK_INTERVAL_MS = 1500;

export function useLiveProgress(tickets: TicketContext[] | undefined) {
  const reducedMotion = useReducedMotion();
  const [progressByKey, setProgressByKey] = useState<Record<string, number>>({});
  // Keep the latest ticket list in a ref so the interval callback reads
  // fresh data without resetting the timer on every render.
  const ticketsRef = useRef<TicketContext[] | undefined>(tickets);
  ticketsRef.current = tickets;

  // Seed newly-seen tickets with their initial progress value, and drop
  // progress for tickets that disappeared.
  useEffect(() => {
    if (!tickets) return;
    setProgressByKey((prev) => {
      const next: Record<string, number> = {};
      let changed = false;
      for (const t of tickets) {
        if (t.ticket_key in prev) {
          next[t.ticket_key] = prev[t.ticket_key] ?? 0;
        } else {
          next[t.ticket_key] = initialProgress(t.state);
          changed = true;
        }
      }
      // Trim removed tickets.
      if (Object.keys(prev).length !== Object.keys(next).length) changed = true;
      return changed ? next : prev;
    });
  }, [tickets]);

  useEffect(() => {
    if (reducedMotion) return;
    const id = setInterval(() => {
      const list = ticketsRef.current;
      if (!list || list.length === 0) return;
      setProgressByKey((prev) => {
        let changed = false;
        const next = { ...prev };
        for (const t of list) {
          if (!isProgressActive(t.state)) continue;
          const cur = next[t.ticket_key] ?? initialProgress(t.state);
          const bumped = advanceProgress(cur);
          if (bumped !== cur) {
            next[t.ticket_key] = bumped;
            changed = true;
          }
        }
        return changed ? next : prev;
      });
    }, TICK_INTERVAL_MS);
    return () => clearInterval(id);
  }, [reducedMotion]);

  return progressByKey;
}
