import {
  type AttemptGroup,
  type GroupedItem,
  type Item,
  type ToolGroup,
  type ToolItem,
  isAnchorTool,
} from "./types";

/**
 * Two-pass folding of ``Item[]`` into ``GroupedItem[]``.
 *
 * Pass 1 folds adjacent non-anchor tool calls into a ``tool_group`` bucket.
 * An "anchor" is any ``message`` item OR a ``Skill`` tool call — per ENG-132,
 * these headline events each earn their own row and terminate whatever tool
 * group came before. ``completed`` and ``retry_boundary`` events also close
 * the open group because the dispatch (or attempt) is ending.
 *
 * Pass 2 folds every grouped entry that precedes a ``retry_boundary`` into
 * an ``attempt_group`` — the previous attempt's noise gets hidden by default
 * so the user's attention lands on the fresh attempt beneath the divider.
 * The boundary item itself is surfaced at the top level between attempts.
 */
export function groupItems(items: Item[]): GroupedItem[] {
  const groupedByTool: GroupedItem[] = [];
  let currentToolGroup: ToolItem[] | null = null;

  const flushToolGroup = () => {
    if (!currentToolGroup || currentToolGroup.length === 0) {
      currentToolGroup = null;
      return;
    }
    if (currentToolGroup.length === 1) {
      // Single follow-up tool doesn't need a wrapper — it's not "spam".
      const only = currentToolGroup[0];
      if (only) groupedByTool.push(only);
    } else {
      const group: ToolGroup = {
        kind: "tool_group",
        ts: currentToolGroup[0]?.ts ?? "",
        tools: currentToolGroup,
      };
      groupedByTool.push(group);
    }
    currentToolGroup = null;
  };

  let sawAnchor = false;
  for (const item of items) {
    if (item.kind === "tool") {
      if (!sawAnchor || isAnchorTool(item)) {
        // Before the first anchor OR on an anchor tool itself — emit inline
        // and (for anchors) mark subsequent non-anchor tools as groupable.
        flushToolGroup();
        groupedByTool.push(item);
        if (isAnchorTool(item)) sawAnchor = true;
      } else {
        // Non-anchor tool following an anchor → accumulate into the open group.
        currentToolGroup = currentToolGroup ?? [];
        currentToolGroup.push(item);
      }
    } else if (item.kind === "message") {
      flushToolGroup();
      groupedByTool.push(item);
      sawAnchor = true;
    } else {
      // error / completed / retry_boundary — all close the open group, then
      // emit inline. Completed/retry_boundary also reset the anchor state so
      // a fresh attempt doesn't inherit its predecessor's anchor lock.
      flushToolGroup();
      groupedByTool.push(item);
      if (item.kind === "completed" || item.kind === "retry_boundary") {
        sawAnchor = false;
      }
    }
  }
  flushToolGroup();

  // Pass 2 — fold prior-attempt entries into attempt_group wrappers.
  const withAttemptGroups: GroupedItem[] = [];
  let attemptNumber = 1;
  let bucket: GroupedItem[] = [];

  for (const entry of groupedByTool) {
    if (entry.kind === "retry_boundary") {
      if (bucket.length > 0) {
        const group: AttemptGroup = {
          kind: "attempt_group",
          ts: bucket[0]?.ts ?? entry.ts,
          attempt: attemptNumber,
          items: bucket,
        };
        withAttemptGroups.push(group);
      }
      withAttemptGroups.push(entry);
      attemptNumber = entry.attempt;
      bucket = [];
    } else {
      bucket.push(entry);
    }
  }
  withAttemptGroups.push(...bucket);

  return withAttemptGroups;
}

/** Count tool calls by ``tool_name`` prefix for the group header badge. */
export function summariseToolCounts(tools: ToolItem[]): string {
  const counts: Record<string, number> = {};
  for (const t of tools) {
    const bucket = t.toolName.startsWith("mcp__") ? "mcp" : t.toolName;
    counts[bucket] = (counts[bucket] ?? 0) + 1;
  }
  const parts = Object.entries(counts)
    .sort(([, a], [, b]) => b - a)
    .map(([name, n]) => `${name}: ${n}`);
  return parts.join(" · ");
}

/** True iff any tool call in the group ended in error — triggers auto-expand. */
export function groupHasError(tools: ToolItem[]): boolean {
  return tools.some((t) => t.isError);
}
