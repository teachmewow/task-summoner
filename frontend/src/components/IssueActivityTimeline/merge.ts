import type { ActivityEvent } from "~/lib/activity";
import type { Item } from "./types";

/**
 * Merge raw ``ActivityEvent`` records into display ``Item`` rows.
 *
 * Pairs ``tool_use`` with its matching ``tool_result`` (by ``tool_use_id``)
 * so each tool call renders as a single collapsible card. Unpaired results
 * become orphan rows so nothing silently disappears on a server hiccup.
 *
 * ``resultIds`` is the shared de-dupe set from the component — passed in
 * rather than owned here so the caller can reset it on ``issueKey`` change.
 */
export function mergeIntoItems(events: ActivityEvent[], resultIds: Set<string>): Item[] {
  const items: Item[] = [];
  const toolIndex: Map<string, number> = new Map();

  for (const ev of events) {
    if (ev.type === "message") {
      items.push({
        kind: "message",
        ts: ev.ts,
        agent: ev.agent || "",
        content: ev.content ?? "",
      });
    } else if (ev.type === "tool_use") {
      const toolName = ev.tool_name ?? ev.content ?? "Tool";
      const id = ev.tool_use_id ?? `${ev.ts}-${toolName}`;
      items.push({
        kind: "tool",
        ts: ev.ts,
        agent: ev.agent || "",
        toolUseId: ev.tool_use_id ?? null,
        toolName,
        toolInput: (ev.tool_input ?? null) as Record<string, unknown> | null,
        toolResult: null,
        isError: false,
        running: true,
      });
      toolIndex.set(id, items.length - 1);
    } else if (ev.type === "tool_result") {
      const id = ev.tool_use_id ?? "";
      const idx = id ? toolIndex.get(id) : undefined;
      if (idx != null) {
        const prev = items[idx];
        if (prev && prev.kind === "tool") {
          prev.toolResult = ev.tool_result ?? ev.content ?? "";
          prev.isError = !!ev.is_error;
          prev.running = false;
          if (id) resultIds.add(id);
        }
      } else {
        items.push({
          kind: "tool",
          ts: ev.ts,
          agent: ev.agent || "",
          toolUseId: ev.tool_use_id ?? null,
          toolName: ev.tool_name ?? "Tool",
          toolInput: null,
          toolResult: ev.tool_result ?? ev.content ?? "",
          isError: !!ev.is_error,
          running: false,
        });
      }
    } else if (ev.type === "error") {
      items.push({ kind: "error", ts: ev.ts, message: ev.content || "Agent error" });
    } else if (ev.type === "completed") {
      const meta = (ev.metadata ?? {}) as Record<string, unknown>;
      const success = typeof meta.success === "boolean" ? (meta.success as boolean) : true;
      items.push({
        kind: "completed",
        ts: ev.ts,
        success,
        content: ev.content ?? "",
      });
    } else if (ev.type === "retry_boundary") {
      items.push({
        kind: "retry_boundary",
        ts: ev.ts,
        state: ev.state ?? "",
        attempt: typeof ev.attempt === "number" ? ev.attempt : 1,
        reason: ev.reason ?? "",
      });
    }
  }

  return items;
}
