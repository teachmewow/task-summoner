import { CheckCircle2, ChevronDown, ChevronRight, XCircle } from "lucide-react";
import { useState } from "react";
import { PHASE_COLOR_VAR, phaseFromOrchestratorState } from "~/lib/phases";
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
 *
 * REVAMP M3 / ENG-182: rendered as a marker node on the Activity
 * Timeline's vertical ley-line. The marker dot is phase-colored (doc =
 * amber, plan = violet, implement = cyan) via the same
 * ``phaseFromOrchestratorState`` helper the PhaseStrip and TicketCard
 * use. Failed steps overlay an ember warning; done steps a mana-green
 * check. Anchor position (``left: -12px``) sits the dot flush against
 * the rail in ``Timeline/index.tsx``.
 */
export function StepGroupBox({ group }: { group: StepGroup }) {
  const [expanded, setExpanded] = useState(!group.success);
  const label = prettyLabel(group.state);
  const phase = phaseFromOrchestratorState(group.state);
  const markerColor = phase ? PHASE_COLOR_VAR[phase] : "var(--color-rune-line-strong)";
  const stats = [
    group.turns != null ? `${group.turns} turns` : null,
    group.costUsd != null ? `$${group.costUsd.toFixed(2)}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <li
      data-timeline-step-group
      data-step-state={group.state}
      data-expanded={expanded ? "true" : "false"}
      className="relative flex flex-col gap-2 rounded-xl border border-rune-line bg-obsidian-raised p-2"
    >
      {/* Ley-line marker dot — sits on top of the vertical rail rendered
          by the timeline container. */}
      <span
        aria-hidden="true"
        className="absolute top-3.5 -left-[14px] h-2.5 w-2.5 rounded-full"
        style={{
          background: markerColor,
          boxShadow: group.success ? `0 0 8px ${markerColor}88` : "0 0 8px var(--color-ember)",
          border: "2px solid var(--color-obsidian)",
        }}
      />
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center justify-between gap-2 rounded px-1 text-left"
      >
        <span className="flex items-center gap-2 text-xs">
          {expanded ? (
            <ChevronDown size={12} strokeWidth={2} className="text-ghost-dim" />
          ) : (
            <ChevronRight size={12} strokeWidth={2} className="text-ghost-dim" />
          )}
          <span
            className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wider"
            style={{
              borderColor: markerColor,
              color: markerColor,
            }}
          >
            {group.success ? (
              <CheckCircle2 size={10} strokeWidth={2} />
            ) : (
              <XCircle size={10} strokeWidth={2} className="text-ember" />
            )}
            {label}
          </span>
          {stats ? <span className="font-mono text-[10px] text-ghost-dimmer">{stats}</span> : null}
        </span>
        <span className="font-mono text-[10px] uppercase tracking-wider text-ghost-dimmer">
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
    .map((word, i) => (i === 0 ? (word[0]?.toUpperCase() ?? "") + word.slice(1) : word))
    .join(" ");
}
