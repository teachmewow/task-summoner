import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Terminal,
  Wrench,
} from "lucide-react";
import { marked } from "marked";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { type ActivityEvent, activityStreamUrl, fetchActivityHistory } from "~/lib/activity";

/**
 * Streaming activity timeline for a single issue.
 *
 * Product intent (see ENG-121): the user wants to see what the agent is doing
 * while it works. Each ``message`` event becomes a markdown-rendered card;
 * each ``tool_use`` becomes a collapsible box whose header is ``<Tool>:
 * <single-line summary>`` and whose body shows the full input, followed by
 * the tool's result once it arrives. ``completed`` / ``error`` events close
 * out the transcript.
 *
 * Scroll behaviour matches a chat UI: auto-pin to bottom as new events arrive,
 * detach once the user scrolls up, and re-engage when they scroll back to the
 * end. We deliberately avoid a "scroll to bottom" button for v0 — the feature
 * is rare enough that clicking the last message works equally well.
 */

interface Props {
  issueKey: string;
}

export function IssueActivityTimeline({ issueKey }: Props) {
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const autoScrollRef = useRef(true);
  // Track tool_use_ids we've already merged a result into so a late result
  // with the same id (unlikely but possible with retries) doesn't clobber.
  const resultIdsRef = useRef(new Set<string>());

  // Replay history on mount — the SSE endpoint also replays, but doing the
  // HTTP fetch first gives us a fast non-streaming render path and lets the
  // SSE connection be opened once the initial paint is done.
  useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    setEvents([]);
    resultIdsRef.current = new Set();
    fetchActivityHistory(issueKey)
      .then((history) => {
        if (cancelled) return;
        setEvents(history);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(err instanceof Error ? err.message : "Failed to load history");
      });
    return () => {
      cancelled = true;
    };
  }, [issueKey]);

  // Open the SSE connection and append each frame. We ignore frames that
  // share a ``ts`` + ``type`` with a trailing event we already have — that
  // happens when the endpoint's replay overlaps with the HTTP history fetch.
  useEffect(() => {
    const source = new EventSource(activityStreamUrl(issueKey));
    const handleEvent = (e: MessageEvent) => {
      try {
        const record = JSON.parse(e.data) as ActivityEvent;
        setEvents((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.ts === record.ts && last.type === record.type) {
            return prev;
          }
          return [...prev, record];
        });
      } catch (err) {
        console.error("timeline parse error", err);
      }
    };
    const TYPES = ["message", "tool_use", "tool_result", "error", "completed"];
    for (const t of TYPES) source.addEventListener(t, handleEvent);
    source.addEventListener("open", () => setConnected(true));
    source.addEventListener("error", () => setConnected(false));
    return () => {
      for (const t of TYPES) source.removeEventListener(t, handleEvent);
      source.close();
    };
  }, [issueKey]);

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    // 32px slack so the "we're basically at the bottom" check isn't brittle.
    autoScrollRef.current = distanceFromBottom < 32;
  }, []);

  // Auto-pin to bottom when new events arrive, unless the user has scrolled up.
  // The body doesn't reference ``events`` directly — we depend on it so this
  // runs on every append.
  // biome-ignore lint/correctness/useExhaustiveDependencies: depend on events to retrigger
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !autoScrollRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, [events]);

  // Merge tool_use + tool_result pairs so the UI renders one collapsible box
  // per call. Unpaired tool_use entries (agent still working on it) render
  // as "running"; unpaired tool_result entries (server hiccup) render as
  // orphans with the raw payload.
  const items = useMemo(() => mergeIntoItems(events, resultIdsRef.current), [events]);

  if (loadError) {
    return (
      <section className="rounded-lg border border-ember-red/40 bg-void-800/70 p-5 text-sm text-ember-red">
        Timeline unavailable: {loadError}
      </section>
    );
  }

  return (
    <section
      data-timeline
      className="flex flex-col gap-3 rounded-lg border border-shadow-purple/60 bg-void-800/70 p-4"
    >
      <header className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Terminal size={14} strokeWidth={2} className="text-arise-violet" />
          <h2 className="text-sm font-semibold uppercase tracking-wider text-arise-violet-bright">
            Agent activity
          </h2>
        </div>
        <span
          className="inline-flex items-center gap-1 text-[10px] text-soul-cyan/70"
          data-stream-status={connected ? "open" : "closed"}
        >
          <span
            className={[
              "h-1.5 w-1.5 rounded-full",
              connected ? "bg-mana-green shadow-[0_0_6px_#34d399]" : "bg-soul-cyan/40",
            ].join(" ")}
          />
          {connected ? "streaming" : "idle"}
        </span>
      </header>

      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="scroll-arise max-h-[640px] min-h-[240px] overflow-y-auto pr-1"
        data-timeline-scroller
      >
        {items.length === 0 ? (
          <EmptyState />
        ) : (
          <ol className="flex flex-col gap-3">
            {items.map((item, idx) => (
              <TimelineItem key={`${item.ts}-${idx}`} item={item} />
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}

function EmptyState() {
  return (
    <div
      data-timeline-empty
      className="rounded-md border border-shadow-purple/60 bg-void-900/40 p-4 text-sm text-soul-cyan/80"
    >
      <p className="mb-1 font-medium text-ghost-white">Waiting for agent to dispatch…</p>
      <p className="text-xs text-soul-cyan/70">
        Messages and tool calls will appear here in real time while the orchestrator runs.
      </p>
    </div>
  );
}

type Item =
  | { kind: "message"; ts: string; agent: string; content: string }
  | {
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
  | { kind: "error"; ts: string; message: string }
  | { kind: "completed"; ts: string; success: boolean; content: string };

function mergeIntoItems(events: ActivityEvent[], resultIds: Set<string>): Item[] {
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
        // Orphan: render it as its own item so nothing is silently lost.
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
    }
  }

  return items;
}

function TimelineItem({ item }: { item: Item }) {
  if (item.kind === "message") return <MessageCard agent={item.agent} content={item.content} />;
  if (item.kind === "tool") return <ToolBox item={item} />;
  if (item.kind === "error")
    return (
      <li
        data-timeline-error
        className="rounded-md border border-ember-red/50 bg-ember-red/10 p-3 text-xs text-ember-red"
      >
        <span className="mr-1 inline-flex items-center gap-1 font-semibold">
          <AlertTriangle size={12} strokeWidth={2} />
          Error
        </span>
        {item.message}
      </li>
    );
  return (
    <li
      data-timeline-completed
      className="flex items-center gap-2 rounded-md border border-mana-green/30 bg-mana-green/5 p-2 text-xs text-mana-green"
    >
      <CheckCircle2 size={12} strokeWidth={2} />
      {item.success ? "Dispatch completed" : "Dispatch ended with failure"}
    </li>
  );
}

function MessageCard({ agent, content }: { agent: string; content: string }) {
  const html = useMemo(
    () => (content ? (marked.parse(content, { gfm: true, breaks: false }) as string) : ""),
    [content],
  );
  return (
    <li
      data-timeline-message
      className="rounded-md border border-shadow-purple/50 bg-void-900/40 p-3"
    >
      {agent ? (
        <p className="mb-1 text-[10px] uppercase tracking-wider text-arise-violet-bright/80">
          {agent}
        </p>
      ) : null}
      {html ? (
        <div
          // biome-ignore lint/security/noDangerouslySetInnerHtml: rendering trusted agent output
          dangerouslySetInnerHTML={{ __html: html }}
          className="prose-rfc max-w-none text-sm text-soul-cyan/90"
        />
      ) : (
        <p className="text-xs text-soul-cyan/60">(empty message)</p>
      )}
    </li>
  );
}

function ToolBox({
  item,
}: {
  item: Extract<Item, { kind: "tool" }>;
}) {
  const [open, setOpen] = useState(false);
  const summary = summariseToolInput(item.toolName, item.toolInput);
  const Chevron = open ? ChevronDown : ChevronRight;

  return (
    <li
      data-timeline-tool
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
        <span className="font-semibold text-ghost-white">{item.toolName}</span>
        {summary ? <span className="truncate text-soul-cyan/70">{summary}</span> : null}
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
          <div className="mb-2">
            <p className="mb-1 text-[10px] uppercase tracking-wider text-arise-violet-bright/70">
              Input
            </p>
            <pre className="overflow-x-auto rounded border border-shadow-purple/40 bg-void-900/60 p-2 text-[11px] text-soul-cyan/90">
              {JSON.stringify(item.toolInput ?? {}, null, 2)}
            </pre>
          </div>
          <div>
            <p className="mb-1 text-[10px] uppercase tracking-wider text-arise-violet-bright/70">
              Result
            </p>
            {item.running ? (
              <p className="text-soul-cyan/60">Waiting for result…</p>
            ) : (
              <pre className="overflow-x-auto rounded border border-shadow-purple/40 bg-void-900/60 p-2 text-[11px] text-soul-cyan/90 whitespace-pre-wrap">
                {item.toolResult ?? "(no output)"}
              </pre>
            )}
          </div>
        </div>
      ) : null}
    </li>
  );
}

/** Keep tool-header summaries to one short line so long inputs don't explode the layout. */
function summariseToolInput(
  toolName: string,
  input: Record<string, unknown> | null,
): string | null {
  if (!input) return null;
  // Heuristic shortcuts for the tools agents use most often; anything else
  // falls back to the first string value we can find.
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
