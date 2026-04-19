import { ChevronDown, ChevronRight, Wrench } from "lucide-react";
import { useMemo, useState } from "react";
import { renderTool } from "./renderers";
import type { ToolItem } from "./types";

/**
 * Single-tool card. Header is produced by the registered renderer; the box
 * itself handles open/closed state, the status pill, and the error border.
 */
export function ToolBox({ item }: { item: ToolItem }) {
  const rendered = useMemo(() => renderTool(item), [item]);
  const [open, setOpen] = useState(!rendered.defaultCollapsed);
  const Chevron = open ? ChevronDown : ChevronRight;

  return (
    <li
      data-timeline-tool
      data-tool-name={item.toolName}
      data-open={open}
      data-tool-error={item.isError || undefined}
      className={[
        "rounded-md border bg-void-900/40",
        item.isError ? "border-ember-red/50" : "border-shadow-purple/50",
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
        {rendered.header}
        <span className="ml-auto flex items-center gap-2 text-[10px]">
          {item.running ? (
            <span className="inline-flex items-center gap-1 text-amber-flame">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-flame" />
              running
            </span>
          ) : item.isError ? (
            <span className="text-ember-red">error</span>
          ) : (
            <span className="text-mana-green">done</span>
          )}
        </span>
      </button>
      {open ? (
        <div className="border-t border-shadow-purple/40 px-3 pb-3 pt-2 text-xs">
          {rendered.body}
        </div>
      ) : null}
    </li>
  );
}
