import { RefreshCw } from "lucide-react";
import type { RetryBoundaryItem } from "./types";

/**
 * Horizontal divider rendered between two attempt runs (ENG-136).
 *
 * The backend emits a single ``retry_boundary`` event just before the state
 * handler is re-dispatched from zero; the timeline folds every event before
 * it into an ``AttemptGroup`` and shows this divider in their place.
 */
export function RetryBoundary({ item }: { item: RetryBoundaryItem }) {
  return (
    <li
      data-timeline-retry-boundary
      data-retry-attempt={item.attempt}
      className="relative my-1 flex items-center gap-2"
    >
      <span className="h-px flex-1 bg-amber-flame/40" aria-hidden />
      <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-flame/50 bg-amber-flame/10 px-3 py-1 text-[10px] font-medium uppercase tracking-wider text-amber-flame">
        <RefreshCw size={10} strokeWidth={2} />
        Attempt {item.attempt} — retrying {item.state || "state"}
        {item.reason ? (
          <span className="normal-case text-soul-cyan/80" data-retry-reason={item.reason}>
            {" "}
            (reason: {truncateReason(item.reason)})
          </span>
        ) : null}
      </span>
      <span className="h-px flex-1 bg-amber-flame/40" aria-hidden />
    </li>
  );
}

function truncateReason(reason: string): string {
  // Reason is surfaced from ``ctx.error`` which may be a full multi-line
  // traceback — clip to the first line and max 100 chars so the divider
  // stays a visual beat rather than a wall of text.
  const firstLine = reason.split("\n", 1)[0] ?? reason;
  return firstLine.length > 100 ? `${firstLine.slice(0, 100)}…` : firstLine;
}
