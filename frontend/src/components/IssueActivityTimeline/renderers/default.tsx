import type { ToolItem } from "../types";
import type { ToolRenderer } from "./types";

/**
 * Fallback renderer — the pre-ENG-132 generic behaviour for any tool whose
 * name isn't in the registry. Shows a one-line summary pulled from common
 * input keys (path, command, pattern, url) and the full JSON payload in the
 * expandable body.
 */
export const renderDefault: ToolRenderer = (event) => {
  const summary = summariseToolInput(event.toolName, event.toolInput);
  return {
    defaultCollapsed: true,
    header: (
      <>
        <span className="font-semibold text-ghost-white">{event.toolName}</span>
        {summary ? <span className="truncate text-soul-cyan/70">{summary}</span> : null}
      </>
    ),
    body: <DefaultToolBody event={event} />,
  };
};

function DefaultToolBody({ event }: { event: ToolItem }) {
  return (
    <>
      <div className="mb-2">
        <p className="mb-1 text-[10px] uppercase tracking-wider text-arise-violet-bright/70">
          Input
        </p>
        <pre className="overflow-x-auto rounded border border-shadow-purple/40 bg-void-900/60 p-2 text-[11px] text-soul-cyan/90">
          {JSON.stringify(event.toolInput ?? {}, null, 2)}
        </pre>
      </div>
      <div>
        <p className="mb-1 text-[10px] uppercase tracking-wider text-arise-violet-bright/70">
          Result
        </p>
        {event.running ? (
          <p className="text-soul-cyan/60">Waiting for result…</p>
        ) : (
          <pre className="overflow-x-auto rounded border border-shadow-purple/40 bg-void-900/60 p-2 text-[11px] text-soul-cyan/90 whitespace-pre-wrap">
            {event.toolResult ?? "(no output)"}
          </pre>
        )}
      </div>
    </>
  );
}

/**
 * Keep tool-header summaries to one short line so long inputs don't explode
 * the layout. The heuristic prefers canonical keys for each known tool and
 * falls back to whichever string it can find.
 */
export function summariseToolInput(
  toolName: string,
  input: Record<string, unknown> | null,
): string | null {
  if (!input) return null;
  const first = (keys: string[]) => {
    for (const k of keys) {
      const v = input[k];
      if (typeof v === "string" && v.length > 0) return v;
    }
    return null;
  };
  const path = first(["file_path", "path", "notebook_path"]);
  const command = first(["command"]);
  const pattern = first(["pattern", "query"]);
  const url = first(["url"]);

  let summary: string | null = null;
  if (toolName === "Bash" && command) summary = command;
  else if ((toolName === "Read" || toolName === "Edit" || toolName === "Write") && path)
    summary = path;
  else if ((toolName === "Grep" || toolName === "Glob") && pattern) summary = pattern;
  else if (toolName === "WebFetch" && url) summary = url;
  else summary = path ?? command ?? pattern ?? url;

  if (!summary) return null;
  return summary.length > 80 ? `${summary.slice(0, 80)}…` : summary;
}
