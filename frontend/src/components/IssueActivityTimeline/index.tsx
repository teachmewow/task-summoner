import { Terminal } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { type ActivityEvent, activityStreamUrl, fetchActivityHistory } from "~/lib/activity";
import { groupItems } from "./grouping";
import { mergeIntoItems } from "./merge";
import { renderGroupedItem } from "./renderGroupedItem";

/**
 * Streaming activity timeline for a single issue.
 *
 * Product intent (ENG-121/132/136): give the user a readable transcript of
 * what the agent is doing. Each message lands as a markdown card; each tool
 * call routes through a renderer registry (Skill gets an inline label; the
 * rest fall back to a generic collapsible). Bursts of subsidiary tool calls
 * between anchor events collapse into a single "N tool calls" box. Retry
 * boundaries fold the previous attempt into an expandable "Attempt N
 * (failed)" wrapper and auto-scroll so the fresh run is visible.
 *
 * Scroll behaviour matches a chat UI: auto-pin to bottom as new events arrive,
 * detach once the user scrolls up, and re-engage when they scroll back.
 */

interface Props {
  issueKey: string;
}

export function IssueActivityTimeline({ issueKey }: Props) {
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const boundaryRef = useRef<HTMLLIElement | null>(null);
  const autoScrollRef = useRef(true);
  // Track tool_use_ids we've already merged a result into so a late result
  // with the same id (unlikely but possible with retries) doesn't clobber.
  const resultIdsRef = useRef(new Set<string>());
  // Remember the highest attempt we've scrolled to so arriving retry
  // boundaries trigger a single scroll, not one per subsequent event.
  const lastScrolledAttemptRef = useRef<number>(0);

  useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    setEvents([]);
    resultIdsRef.current = new Set();
    lastScrolledAttemptRef.current = 0;
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
    const TYPES = ["message", "tool_use", "tool_result", "error", "completed", "retry_boundary"];
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
    autoScrollRef.current = distanceFromBottom < 32;
  }, []);

  // Merge tool_use + tool_result pairs, then fold into groups (tool bursts +
  // attempt-level buckets). Both steps are pure and driven by ``events``.
  const items = useMemo(() => mergeIntoItems(events, resultIdsRef.current), [events]);
  const groupedItems = useMemo(() => groupItems(items), [items]);

  // Auto-pin to bottom when new events arrive, unless the user has scrolled up.
  // biome-ignore lint/correctness/useExhaustiveDependencies: depend on events to retrigger
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !autoScrollRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, [events]);

  // When a new retry_boundary arrives, scroll it into view once so the user
  // catches "retry starts here" immediately — the generic auto-pin would land
  // them below the boundary on whatever fresh event came next.
  useEffect(() => {
    const latest = latestBoundaryAttempt(events);
    if (latest > lastScrolledAttemptRef.current) {
      lastScrolledAttemptRef.current = latest;
      // Defer until the node is painted.
      queueMicrotask(() => {
        const node = boundaryRef.current;
        // jsdom (tests) doesn't implement scrollIntoView — guard so a
        // missing method doesn't surface as an unhandled rejection.
        if (node && typeof node.scrollIntoView === "function") {
          node.scrollIntoView({ block: "center", behavior: "smooth" });
        }
      });
    }
  }, [events]);

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
        {groupedItems.length === 0 ? (
          <EmptyState />
        ) : (
          <ol
            className="flex flex-col gap-3"
            ref={(node) => {
              // Cache the most recent top-level boundary li for
              // scroll-into-view. We query the DOM instead of threading a
              // ref through the render tree because the boundary renderer
              // is reused inside AttemptGroupBox expanders and we don't
              // want those expanded copies to steal the anchor.
              if (!node) {
                boundaryRef.current = null;
                return;
              }
              const boundaries = node.querySelectorAll(":scope > [data-timeline-retry-boundary]");
              const last = boundaries[boundaries.length - 1] ?? null;
              boundaryRef.current = (last as HTMLLIElement | null) ?? null;
            }}
          >
            {groupedItems.map((entry, idx) => renderGroupedItem(entry, idx))}
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

function latestBoundaryAttempt(events: ActivityEvent[]): number {
  let best = 0;
  for (const ev of events) {
    if (ev.type === "retry_boundary") {
      const attempt = typeof ev.attempt === "number" ? ev.attempt : 1;
      if (attempt > best) best = attempt;
    }
  }
  return best;
}
