import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import { renderGroupedItem } from "./renderGroupedItem";
import type { AttemptGroup } from "./types";

/**
 * Collapsed wrapper around a previous (failed) attempt's entire transcript.
 *
 * When a retry boundary arrives, the user cares about the fresh attempt
 * beneath it — not the noise from the attempt that just failed. We hide
 * that noise behind one click, but keep it accessible so they can still
 * diagnose what went wrong.
 */
export function AttemptGroupBox({ group }: { group: AttemptGroup }) {
  const [open, setOpen] = useState(false);
  const Chevron = open ? ChevronDown : ChevronRight;

  return (
    <li
      data-timeline-attempt-group
      data-attempt={group.attempt}
      data-open={open}
      className="rounded-md border border-rune-line bg-vault/40"
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-ghost-dim hover:bg-arcane/5"
        aria-expanded={open}
      >
        <Chevron size={12} strokeWidth={2} className="shrink-0 text-ghost-dimmer" />
        <span className="font-semibold text-ghost/80">Attempt {group.attempt} (failed)</span>
        <span className="ml-auto text-[10px] text-ghost-dimmer">
          {group.items.length} event{group.items.length === 1 ? "" : "s"}
        </span>
      </button>
      {open ? (
        <ol className="flex flex-col gap-2 border-t border-rune-line px-3 py-2">
          {group.items.map((entry, idx) => renderGroupedItem(entry, idx))}
        </ol>
      ) : null}
    </li>
  );
}
