import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import { renderGroupedItem } from "./renderGroupedItem";
import type { AttemptGroup } from "./types";

/**
 * Collapsed wrapper around a previous (failed) attempt's entire transcript.
 *
 * Product intent (ENG-136): when a retry boundary arrives, the user cares
 * about the fresh attempt beneath it — not the noise from the attempt that
 * just failed. We hide that noise behind one click, but keep it accessible
 * so they can still diagnose what went wrong.
 */
export function AttemptGroupBox({ group }: { group: AttemptGroup }) {
  const [open, setOpen] = useState(false);
  const Chevron = open ? ChevronDown : ChevronRight;

  return (
    <li
      data-timeline-attempt-group
      data-attempt={group.attempt}
      data-open={open}
      className="rounded-md border border-shadow-purple/40 bg-void-900/30"
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-soul-cyan hover:bg-arise-violet/5"
        aria-expanded={open}
      >
        <Chevron size={12} strokeWidth={2} className="text-soul-cyan/60 shrink-0" />
        <span className="font-semibold text-soul-cyan/80">Attempt {group.attempt} (failed)</span>
        <span className="ml-auto text-[10px] text-soul-cyan/50">
          {group.items.length} event{group.items.length === 1 ? "" : "s"}
        </span>
      </button>
      {open ? (
        <ol className="flex flex-col gap-2 border-t border-shadow-purple/40 px-3 py-2">
          {group.items.map((entry, idx) => renderGroupedItem(entry, idx))}
        </ol>
      ) : null}
    </li>
  );
}
