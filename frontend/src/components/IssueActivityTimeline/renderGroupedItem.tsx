import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { marked } from "marked";
import type { ReactNode } from "react";
import { AttemptGroupBox } from "./AttemptGroupBox";
import { RetryBoundary } from "./RetryBoundary";
import { StepGroupBox } from "./StepGroupBox";
import { ToolBox } from "./ToolBox";
import { ToolsGroupBox } from "./ToolsGroupBox";
import type { GroupedItem } from "./types";

/**
 * Dispatch a grouped timeline entry to the right React component.
 *
 * Kept as a plain function (not a component) so both the top-level timeline
 * and the ``AttemptGroupBox`` expander share the same rendering pipeline —
 * expanding a prior attempt should reconstruct the exact same UI the live
 * feed showed at the time, minus the auto-scroll.
 */
export function renderGroupedItem(entry: GroupedItem, idx: number): ReactNode {
  const key = `${entry.ts}-${idx}-${entry.kind}`;
  switch (entry.kind) {
    case "message":
      return <MessageCard key={key} agent={entry.agent} content={entry.content} />;
    case "tool":
      return <ToolBox key={key} item={entry} />;
    case "tool_group":
      return <ToolsGroupBox key={key} tools={entry.tools} />;
    case "error":
      return (
        <li
          key={key}
          data-timeline-error
          className="rounded-md border border-blood/50 bg-blood/10 p-3 text-xs text-blood"
        >
          <span className="mr-1 inline-flex items-center gap-1 font-semibold">
            <AlertTriangle size={12} strokeWidth={2} />
            Error
          </span>
          {entry.message}
        </li>
      );
    case "completed":
      return (
        <li
          key={key}
          data-timeline-completed
          className="flex items-center gap-2 rounded-md border border-phase-done/40 bg-phase-done/5 p-2 text-xs text-phase-done"
        >
          <CheckCircle2 size={12} strokeWidth={2} />
          {entry.success ? "Dispatch completed" : "Dispatch ended with failure"}
        </li>
      );
    case "retry_boundary":
      return <RetryBoundary key={key} item={entry} />;
    case "attempt_group":
      return <AttemptGroupBox key={key} group={entry} />;
    case "step_group":
      return <StepGroupBox key={key} group={entry} />;
  }
}

function MessageCard({ agent, content }: { agent: string; content: string }) {
  const html = content ? (marked.parse(content, { gfm: true, breaks: false }) as string) : "";
  return (
    <li data-timeline-message className="rounded-md border border-rune-line-strong bg-vault/40 p-3">
      {agent ? (
        <p className="mb-1 font-mono text-[10px] uppercase tracking-wider text-arcane/80">
          {agent}
        </p>
      ) : null}
      {html ? (
        <div
          // biome-ignore lint/security/noDangerouslySetInnerHtml: rendering trusted agent output
          dangerouslySetInnerHTML={{ __html: html }}
          className="prose-rfc max-w-none text-sm text-ghost/90"
        />
      ) : (
        <p className="text-xs text-ghost-dim">(empty message)</p>
      )}
    </li>
  );
}
