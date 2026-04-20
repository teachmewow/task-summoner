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
        "rounded-md border bg-vault/40",
        item.isError ? "border-blood/50" : "border-rune-line-strong",
      ].join(" ")}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-ghost-dim hover:bg-arcane/5"
        aria-expanded={open}
      >
        <Chevron size={12} strokeWidth={2} className="shrink-0 text-arcane" />
        <Wrench size={12} strokeWidth={2} className="shrink-0 text-arcane" />
        {rendered.header}
        <span className="ml-auto flex items-center gap-2 text-[10px]">
          {item.running ? (
            <span className="inline-flex items-center gap-1 text-ember">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ember" />
              running
            </span>
          ) : item.isError ? (
            <span className="text-blood">error</span>
          ) : (
            <span className="text-phase-done">done</span>
          )}
        </span>
      </button>
      {open ? (
        <div className="border-t border-rune-line px-3 pb-3 pt-2 text-xs">{rendered.body}</div>
      ) : null}
    </li>
  );
}
