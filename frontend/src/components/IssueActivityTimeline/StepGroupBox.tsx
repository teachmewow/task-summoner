import { CheckCircle2, ChevronDown, ChevronRight, XCircle } from "lucide-react";
import { useState } from "react";
import { renderGroupedItem } from "./renderGroupedItem";
import type { StepGroup } from "./types";

/**
 * Collapsed summary of a finished FSM step (e.g. ``CREATING_DOC``) with a
 * click-to-expand panel that renders the full transcript in-place via the
 * shared ``renderGroupedItem`` dispatcher.
 *
 * Default is collapsed: once the user has moved past a gate they rarely
 * re-read the step-by-step; they want the *next* batch of activity clear.
 * Auto-expand on failure so a fresh error doesn't get hidden.
 */
export function StepGroupBox({ group }: { group: StepGroup }) {
  const [expanded, setExpanded] = useState(!group.success);
  const label = prettyLabel(group.state);
  const stats = [
    group.turns != null ? `${group.turns} turns` : null,
    group.costUsd != null ? `$${group.costUsd.toFixed(2)}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  const StatusIcon = group.success ? CheckCircle2 : XCircle;
  const statusClasses = group.success
    ? "border-mana-green/40 text-mana-green"
    : "border-ember-red/50 text-ember-red";

  return (
    <li
      data-timeline-step-group
      data-step-state={group.state}
      data-expanded={expanded ? "true" : "false"}
      className="flex flex-col gap-2 rounded-md border border-shadow-purple/50 bg-void-900/40 p-2"
    >
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center justify-between gap-2 rounded px-1 text-left"
      >
        <span className="flex items-center gap-2 text-xs">
          {expanded ? (
            <ChevronDown size={12} strokeWidth={2} className="text-arise-violet-bright" />
          ) : (
            <ChevronRight size={12} strokeWidth={2} className="text-arise-violet-bright" />
          )}
          <span
            className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-semibold ${statusClasses}`}
          >
            <StatusIcon size={10} strokeWidth={2} />
            {label}
          </span>
          {stats ? <span className="text-[11px] text-soul-cyan/70">{stats}</span> : null}
        </span>
        <span className="text-[10px] uppercase tracking-wider text-soul-cyan/50">
          {expanded ? "hide" : "show"}
        </span>
      </button>
      {expanded ? (
        <ol className="flex flex-col gap-2 pl-3">
          {group.items.map((entry, idx) => renderGroupedItem(entry, idx))}
        </ol>
      ) : null}
    </li>
  );
}

/** Map ``CREATING_DOC`` → ``Creating doc`` so step chips read naturally. */
function prettyLabel(state: string): string {
  if (!state) return "Step";
  return state
    .toLowerCase()
    .split("_")
    .map((word, i) => (i === 0 ? word[0]?.toUpperCase() + word.slice(1) : word))
    .join(" ");
}
