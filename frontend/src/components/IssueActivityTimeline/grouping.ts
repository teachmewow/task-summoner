import {
  type AttemptGroup,
  type GroupedItem,
  type Item,
  type StepGroup,
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

  // Pass 3 — fold each completed FSM state into a collapsible ``StepGroup``.
  // "Completed" means we saw a ``completed`` event for that state (the
  // adapter emits one at the end of each ``_run_agent``). Items for the
  // *current* (in-flight) state remain ungrouped so the live transcript
  // stays visible without the user having to expand anything.
  return groupClosedSteps(withAttemptGroups);
}

/**
 * Walk the already-grouped stream and wrap runs of same-state entries that
 * end in a ``completed`` event into a ``StepGroup``. The grouping is
 * open-ended — while a state is still active (no ``completed`` seen yet),
 * its entries stay at the top level so the live view doesn't require a
 * click to see the newest tool call. Boundary/error/completed meta-entries
 * belong to the step they end, so they land inside the group.
 */
function groupClosedSteps(entries: GroupedItem[]): GroupedItem[] {
  if (entries.length === 0) return entries;

  const output: GroupedItem[] = [];
  let bucket: GroupedItem[] = [];
  let bucketState: string | null = null;

  const stateOf = (entry: GroupedItem): string => {
    switch (entry.kind) {
      case "message":
      case "tool":
      case "error":
      case "completed":
      case "retry_boundary":
        return entry.state ?? "";
      case "tool_group":
        return entry.tools[0]?.state ?? "";
      case "attempt_group": {
        const first = entry.items[0];
        return first ? stateOf(first) : "";
      }
      case "step_group":
        return entry.state;
    }
  };

  const flushAsStep = (closer: Extract<GroupedItem, { kind: "completed" }>) => {
    if (bucketState == null) return;
    const group: StepGroup = {
      kind: "step_group",
      ts: bucket[0]?.ts ?? closer.ts,
      state: bucketState,
      items: [...bucket, closer],
      success: closer.success,
      costUsd: closer.costUsd,
      turns: closer.turns,
    };
    output.push(group);
    bucket = [];
    bucketState = null;
  };

  for (const entry of entries) {
    const entryState = stateOf(entry);
    // ``completed`` closes the current state's bucket into a StepGroup — the
    // completed entry itself is the group's tail so the summary has the
    // final cost/turns telemetry.
    if (entry.kind === "completed") {
      if (bucketState == null || bucketState === entryState) {
        bucketState = entryState || bucketState;
        flushAsStep(entry);
      } else {
        // State changed without a completed for the previous bucket (rare —
        // e.g., orchestrator crashed). Emit the orphaned bucket as live
        // items and start fresh.
        output.push(...bucket);
        bucket = [];
        bucketState = entryState;
        flushAsStep(entry);
      }
      continue;
    }

    if (bucketState == null || entryState === "" || entryState === bucketState) {
      // Same state (or a state-less meta entry) — accumulate.
      bucket.push(entry);
      if (bucketState == null && entryState) bucketState = entryState;
    } else {
      // State changed without a ``completed`` closer — emit prior as live
      // items so nothing is hidden, then open a new bucket.
      output.push(...bucket);
      bucket = [entry];
      bucketState = entryState;
    }
  }

  // Anything left over belongs to the still-active state — keep live.
  output.push(...bucket);
  return output;
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
