/**
 * Shared types for the issue activity timeline.
 *
 * The timeline merges raw ``ActivityEvent`` records (one per agent event) into
 * a list of ``Item`` rows — each row is what we actually paint. A plain
 * ``tool_use`` becomes a ``tool`` item; a ``tool_use`` + ``tool_result`` pair
 * collapses into the same ``tool`` item with ``running: false``.
 *
 * Items are grouped post-merge into ``GroupedItem`` entries: sequences of
 * subsidiary tool calls between anchor events get wrapped in a
 * ``tool_group`` bucket, and everything that precedes a ``retry_boundary``
 * gets folded into an ``attempt_group`` so the previous attempt's noise
 * is hidden by default.
 */

export interface ToolItem {
  kind: "tool";
  ts: string;
  agent: string;
  toolUseId: string | null;
  toolName: string;
  toolInput: Record<string, unknown> | null;
  toolResult: string | null;
  isError: boolean;
  running: boolean;
}

export interface MessageItem {
  kind: "message";
  ts: string;
  agent: string;
  content: string;
}

export interface ErrorItem {
  kind: "error";
  ts: string;
  message: string;
}

export interface CompletedItem {
  kind: "completed";
  ts: string;
  success: boolean;
  content: string;
}

export interface RetryBoundaryItem {
  kind: "retry_boundary";
  ts: string;
  state: string;
  attempt: number;
  reason: string;
}

/** Flat items produced by ``mergeIntoItems`` before grouping. */
export type Item = MessageItem | ToolItem | ErrorItem | CompletedItem | RetryBoundaryItem;

export interface ToolGroup {
  kind: "tool_group";
  ts: string;
  tools: ToolItem[];
}

export interface AttemptGroup {
  kind: "attempt_group";
  ts: string;
  attempt: number;
  items: GroupedItem[];
}

/** Items after grouping — sub-tool clusters and prior attempts are wrapped. */
export type GroupedItem = Item | ToolGroup | AttemptGroup;

/** Tool names starting with these prefixes are treated as anchor events. */
export const ANCHOR_TOOL_NAMES: ReadonlySet<string> = new Set(["Skill"]);

/**
 * Inspect a tool item and decide whether it acts as an anchor (stays inline,
 * flushes any open tool group). ``Skill`` is the only anchor tool today, but
 * we expose this as a set so future renderers can opt in.
 */
export function isAnchorTool(item: ToolItem): boolean {
  return ANCHOR_TOOL_NAMES.has(item.toolName);
}
