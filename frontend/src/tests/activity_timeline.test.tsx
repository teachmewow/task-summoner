import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { IssueActivityTimeline } from "~/components/IssueActivityTimeline";
import type { ActivityEvent } from "~/lib/activity";

/**
 * Behaviour tests for the streaming activity timeline (ENG-121).
 *
 * We mock ``EventSource`` so tests can inject live events without hitting a
 * server, and stub ``fetch`` for the replay history call. The goal is to
 * verify the renderer's contract: markdown messages, collapsible tool calls,
 * empty state copy.
 */

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  listeners: Map<string, Array<(e: MessageEvent) => void>> = new Map();
  readyState = 0;
  onopen: ((e: Event) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, handler: (e: MessageEvent) => void) {
    const arr = this.listeners.get(type) ?? [];
    arr.push(handler);
    this.listeners.set(type, arr);
  }

  removeEventListener(type: string, handler: (e: MessageEvent) => void) {
    const arr = this.listeners.get(type);
    if (!arr) return;
    this.listeners.set(
      type,
      arr.filter((h) => h !== handler),
    );
  }

  close() {
    this.readyState = 2;
  }

  // Test helper — fires an event to all subscribers of ``type``.
  emit(type: string, payload: ActivityEvent) {
    const arr = this.listeners.get(type) ?? [];
    const e = new MessageEvent("message", { data: JSON.stringify(payload) });
    for (const h of arr) h(e);
  }
}

function mockHistoryFetch(records: ActivityEvent[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify(records), {
          headers: { "Content-Type": "application/json" },
        }),
    ),
  );
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource as unknown as typeof EventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("IssueActivityTimeline", () => {
  it("renders the waiting-to-dispatch empty state when no history exists", async () => {
    mockHistoryFetch([]);
    render(<IssueActivityTimeline issueKey="ENG-121" />);
    await screen.findByText(/waiting for agent to dispatch/i);
  });

  it("renders persisted messages as markdown cards", async () => {
    mockHistoryFetch([
      {
        ts: "2026-04-19T15:00:00Z",
        type: "message",
        content: "# Planning\nNext step is to **read** the repo.",
        agent: "planner",
      },
    ]);
    render(<IssueActivityTimeline issueKey="ENG-121" />);
    await waitFor(() => {
      const h1 = document.querySelector("[data-timeline-message] h1");
      expect(h1?.textContent).toBe("Planning");
    });
    const strong = document.querySelector("[data-timeline-message] strong");
    expect(strong?.textContent).toBe("read");
  });

  it("collapses tool calls by default and reveals input/result when toggled", async () => {
    mockHistoryFetch([
      {
        ts: "2026-04-19T15:00:01Z",
        type: "tool_use",
        content: "Bash",
        agent: "impl",
        tool_name: "Bash",
        tool_use_id: "t-1",
        tool_input: { command: "ls -la" },
      },
      {
        ts: "2026-04-19T15:00:02Z",
        type: "tool_result",
        content: "Bash",
        agent: "impl",
        tool_name: "Bash",
        tool_use_id: "t-1",
        tool_result: "total 16\ndrwx foo",
        is_error: false,
      },
    ]);
    render(<IssueActivityTimeline issueKey="ENG-121" />);

    // Header summary visible up-front.
    await screen.findByText(/ls -la/i);
    // Result panel is hidden until clicked.
    expect(document.querySelectorAll("pre").length).toBe(0);

    // Expand by clicking the header button.
    const header = screen.getByRole("button", { expanded: false });
    await act(async () => header.click());

    // Now both the input and result panels are visible.
    await waitFor(() => {
      const panes = document.querySelectorAll("[data-timeline-tool][data-open='true'] pre");
      expect(panes.length).toBe(2);
    });
    expect(document.body.textContent).toContain("total 16");
  });

  it("appends live events received over the stream", async () => {
    mockHistoryFetch([]);
    render(<IssueActivityTimeline issueKey="ENG-121" />);
    // Wait for the EventSource to be constructed.
    await waitFor(() => expect(FakeEventSource.instances.length).toBe(1));

    const src = FakeEventSource.instances[0];
    if (!src) throw new Error("EventSource never constructed");
    await act(async () => {
      src.emit("message", {
        ts: "2026-04-19T15:01:00Z",
        type: "message",
        content: "hello from the agent",
        agent: "planner",
      });
    });
    await screen.findByText(/hello from the agent/i);
  });

  it("marks a tool call as running when no result has arrived yet", async () => {
    mockHistoryFetch([
      {
        ts: "2026-04-19T15:00:03Z",
        type: "tool_use",
        content: "Read",
        agent: "impl",
        tool_name: "Read",
        tool_use_id: "t-2",
        tool_input: { file_path: "plan.md" },
      },
    ]);
    render(<IssueActivityTimeline issueKey="ENG-121" />);
    await screen.findByText(/plan.md/i);
    expect(document.body.textContent).toMatch(/running/i);
  });
});
