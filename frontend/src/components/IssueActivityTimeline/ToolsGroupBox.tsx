import { ChevronDown, ChevronRight, Wrench } from "lucide-react";
import { useMemo, useState } from "react";
import { ToolBox } from "./ToolBox";
import { groupHasError, summariseToolCounts } from "./grouping";
import type { ToolItem } from "./types";

/**
 * Collapsible container for a run of subsidiary tool calls.
 *
 * Product intent (ENG-132 / Part B): after an anchor event (assistant message
 * or top-level Skill), agents frequently emit 20+ tiny Read/Bash/mcp calls
 * that flood the timeline. This box keeps them hidden by default and surfaces
 * just a count + per-type breakdown — the user can expand on demand.
 *
 * Two escape hatches override the collapsed default:
 *   - any tool in the group errored → auto-expand so the failure isn't hidden
 *   - the user clicks the header → manual toggle
 */
export function ToolsGroupBox({ tools }: { tools: ToolItem[] }) {
  const hasError = useMemo(() => groupHasError(tools), [tools]);
  const [open, setOpen] = useState(hasError);
  // If a new error lands after the initial render, bump open to true once.
  // We avoid forcing-re-close so the user's manual close still sticks.
  if (hasError && !open) setOpen(true);

  const Chevron = open ? ChevronDown : ChevronRight;
  const total = tools.length;
  const breakdown = useMemo(() => summariseToolCounts(tools), [tools]);

  return (
    <li
      data-timeline-tool-group
      data-open={open}
      data-group-error={hasError || undefined}
      data-group-size={total}
      className={[
        "rounded-md border bg-void-900/40",
        hasError ? "border-ember-red/50" : "border-shadow-purple/50",
      ].join(" ")}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-soul-cyan hover:bg-arise-violet/5"
        aria-expanded={open}
      >
        <Chevron size={12} strokeWidth={2} className="text-arise-violet shrink-0" />
        <Wrench size={12} strokeWidth={2} className="text-arise-violet shrink-0" />
        <span className="font-semibold text-ghost-white">
          {total} tool call{total === 1 ? "" : "s"}
        </span>
        {breakdown ? <span className="truncate text-soul-cyan/70">({breakdown})</span> : null}
        {hasError ? <span className="ml-auto text-[10px] text-ember-red">error</span> : null}
      </button>
      {open ? (
        <ol className="flex flex-col gap-2 border-t border-shadow-purple/40 px-3 py-2">
          {tools.map((tool, idx) => (
            <ToolBox key={`${tool.ts}-${idx}`} item={tool} />
          ))}
        </ol>
      ) : null}
    </li>
  );
}
