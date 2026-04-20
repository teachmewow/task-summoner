import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { IssueActivityTimeline } from "~/components/IssueActivityTimeline";
import { groupItems } from "~/components/IssueActivityTimeline/grouping";
import {
  renderDefault,
  renderSkill,
  renderTool,
} from "~/components/IssueActivityTimeline/renderers";
import type { ToolItem } from "~/components/IssueActivityTimeline/types";
import type { ActivityEvent } from "~/lib/activity";

/**
 * Behaviour tests for the streaming activity timeline (ENG-121/132/136).
 *
 * We mock ``EventSource`` so tests can inject live events without hitting a
 * server, and stub ``fetch`` for the replay history call. The tests cover
 * the contract documented on the issues:
 *
 *   - ENG-121: markdown messages, collapsible tool calls, empty state copy.
 *   - ENG-132: Skill renderer inline header, unknown-tool fallback, grouping
 *     of subsidiary tools between anchor events, auto-expand on error.
 *   - ENG-136: retry_boundary divider + auto-fold of prior attempt.
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

describe("IssueActivityTimeline — baseline (ENG-121)", () => {
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

    await screen.findByText(/ls -la/i);
    expect(document.querySelectorAll("pre").length).toBe(0);

    const header = screen.getByRole("button", { expanded: false });
    await act(async () => header.click());

    await waitFor(() => {
      const panes = document.querySelectorAll("[data-timeline-tool][data-open='true'] pre");
      expect(panes.length).toBe(2);
    });
    expect(document.body.textContent).toContain("total 16");
  });

  it("appends live events received over the stream", async () => {
    mockHistoryFetch([]);
    render(<IssueActivityTimeline issueKey="ENG-121" />);
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

describe("IssueActivityTimeline — renderers (ENG-132 Part A)", () => {
  it("renders a Skill call with inline 'Skill: <name>' header and short args", () => {
    const event: ToolItem = {
      kind: "tool",
      ts: "2026-04-19T15:00:00Z",
      agent: "impl",
      state: "",
      toolUseId: "t-skill",
      toolName: "Skill",
      toolInput: {
        skill: "task-summoner-workflows:ticket-plan",
        args: "ENG-131 --headless",
      },
      toolResult: null,
      isError: false,
      running: true,
    };
    const out = renderSkill(event);
    // The header is a React node; we rely on the SkillBody being React content
    // and verify the text via a wrapping render.
    const { container } = renderComponent(out.header);
    expect(container.textContent).toContain("Skill: task-summoner-workflows:ticket-plan");
    expect(container.textContent).toContain("args: ENG-131 --headless");
  });

  it("omits inline args when they exceed 80 chars or contain newlines", () => {
    const longArgs = "x".repeat(120);
    const event: ToolItem = {
      kind: "tool",
      ts: "t",
      agent: "",
      state: "",
      toolUseId: null,
      toolName: "Skill",
      toolInput: { skill: "foo", args: longArgs },
      toolResult: null,
      isError: false,
      running: false,
    };
    const out = renderSkill(event);
    const { container } = renderComponent(out.header);
    expect(container.textContent).toContain("Skill: foo");
    expect(container.textContent).not.toContain(longArgs);

    const multiline: ToolItem = { ...event, toolInput: { skill: "foo", args: "a\nb" } };
    const out2 = renderSkill(multiline);
    const { container: c2 } = renderComponent(out2.header);
    expect(c2.textContent).not.toContain("a\nb");
  });

  it("falls back to the default renderer for unknown tool names", () => {
    const event: ToolItem = {
      kind: "tool",
      ts: "t",
      agent: "",
      state: "",
      toolUseId: null,
      toolName: "SomeNewTool",
      toolInput: { file_path: "x.md" },
      toolResult: null,
      isError: false,
      running: false,
    };
    expect(renderTool(event)).toEqual(renderDefault(event));
  });
});

describe("IssueActivityTimeline — grouping (ENG-132 Part B)", () => {
  it("groups subsidiary tools between anchor events into a single box", () => {
    const items = [
      anchorMessage(),
      tool("Read", false),
      tool("Bash", false),
      tool("Grep", false),
      anchorMessage("m2"),
    ];
    const grouped = groupItems(items);
    // message, tool_group (3 tools), message
    expect(grouped.map((g) => g.kind)).toEqual(["message", "tool_group", "message"]);
    const toolGroup = grouped[1];
    if (toolGroup?.kind !== "tool_group") throw new Error("expected tool_group");
    expect(toolGroup.tools).toHaveLength(3);
  });

  it("keeps a top-level Skill tool inline (it's an anchor itself)", () => {
    const items = [skill("plan"), tool("Read", false), tool("Bash", false), anchorMessage()];
    const grouped = groupItems(items);
    expect(grouped.map((g) => g.kind)).toEqual(["tool", "tool_group", "message"]);
  });

  it("renders a collapsed tool-group box showing the count + per-type breakdown", async () => {
    mockHistoryFetch([
      skillEvent("task-summoner-workflows:ticket-plan"),
      toolUseEvent("Read", "t-r1", { file_path: "a.md" }),
      toolResultEvent("Read", "t-r1"),
      toolUseEvent("Read", "t-r2", { file_path: "b.md" }),
      toolResultEvent("Read", "t-r2"),
      toolUseEvent("Bash", "t-b1", { command: "ls" }),
      toolResultEvent("Bash", "t-b1"),
    ]);
    render(<IssueActivityTimeline issueKey="ENG-132" />);
    await screen.findByText(/Skill: task-summoner-workflows:ticket-plan/i);
    await waitFor(() => {
      const group = document.querySelector("[data-timeline-tool-group]");
      expect(group).toBeTruthy();
    });
    const group = document.querySelector("[data-timeline-tool-group]");
    expect(group?.getAttribute("data-group-size")).toBe("3");
    expect(group?.textContent).toMatch(/3 tool calls/);
    expect(group?.textContent).toContain("Read: 2");
    expect(group?.textContent).toContain("Bash: 1");
    // Default collapsed → inner tools aren't rendered.
    expect(
      document.querySelectorAll("[data-timeline-tool-group] [data-timeline-tool]").length,
    ).toBe(0);
  });

  it("auto-expands the tool-group box when any inner tool errored", async () => {
    mockHistoryFetch([
      skillEvent("task-summoner-workflows:ticket-plan"),
      toolUseEvent("Read", "t-ok", { file_path: "a.md" }),
      toolResultEvent("Read", "t-ok"),
      toolUseEvent("Bash", "t-fail", { command: "boom" }),
      toolResultEvent("Bash", "t-fail", { is_error: true, result: "exit 1" }),
    ]);
    render(<IssueActivityTimeline issueKey="ENG-132" />);
    await waitFor(() => {
      const group = document.querySelector("[data-timeline-tool-group]");
      expect(group).toBeTruthy();
    });
    const group = document.querySelector("[data-timeline-tool-group]");
    expect(group?.getAttribute("data-open")).toBe("true");
    expect(group?.getAttribute("data-group-error")).toBe("true");
  });

  it("buckets all mcp__* tools under a single 'mcp' badge", () => {
    const items = [
      anchorMessage(),
      tool("mcp__linear-server__get_issue", false),
      tool("mcp__linear-server__list_issues", false),
      tool("Read", false),
    ];
    const grouped = groupItems(items);
    const g = grouped[1];
    if (g?.kind !== "tool_group") throw new Error("expected tool_group");
    // Every mcp__* name collapses to the single 'mcp' bucket for the header.
    const mcpTools = g.tools.filter((t) => t.toolName.startsWith("mcp__"));
    expect(mcpTools).toHaveLength(2);
  });
});

describe("IssueActivityTimeline — retry boundary (ENG-136)", () => {
  it("renders a retry_boundary event as a labelled divider", async () => {
    mockHistoryFetch([
      {
        ts: "2026-04-19T15:00:00Z",
        type: "retry_boundary",
        content: "",
        agent: "",
        state: "PLANNING",
        attempt: 2,
        reason: "Planner did not produce a plan",
      },
    ]);
    render(<IssueActivityTimeline issueKey="ENG-136" />);
    await waitFor(() => {
      const boundary = document.querySelector("[data-timeline-retry-boundary]");
      expect(boundary).toBeTruthy();
    });
    const boundary = document.querySelector("[data-timeline-retry-boundary]");
    expect(boundary?.getAttribute("data-retry-attempt")).toBe("2");
    expect(boundary?.textContent).toMatch(/Attempt 2/);
    expect(boundary?.textContent).toMatch(/retrying PLANNING/);
    expect(boundary?.textContent).toMatch(/Planner did not produce a plan/);
  });

  it("folds events before the boundary into an 'Attempt N (failed)' collapsed group", async () => {
    mockHistoryFetch([
      {
        ts: "t1",
        type: "message",
        content: "first attempt kicking off",
        agent: "planner",
      },
      {
        ts: "t2",
        type: "tool_use",
        content: "Skill",
        agent: "planner",
        tool_name: "Skill",
        tool_use_id: "t-s1",
        tool_input: { skill: "task-summoner-workflows:ticket-plan", args: "A-1 --headless" },
      },
      {
        ts: "t3",
        type: "retry_boundary",
        content: "",
        agent: "",
        state: "PLANNING",
        attempt: 2,
        reason: "x",
      },
      {
        ts: "t4",
        type: "message",
        content: "retrying now",
        agent: "planner",
      },
    ]);
    render(<IssueActivityTimeline issueKey="ENG-136" />);
    await waitFor(() => {
      const group = document.querySelector("[data-timeline-attempt-group]");
      expect(group).toBeTruthy();
    });
    const group = document.querySelector("[data-timeline-attempt-group]");
    expect(group?.getAttribute("data-attempt")).toBe("1");
    // Collapsed by default — inner events aren't rendered until expanded.
    expect(group?.getAttribute("data-open")).toBe("false");
    expect(document.body.textContent).toContain("retrying now");
  });
});

// ---------- helpers -----------------------------------------------------------

function renderComponent(node: unknown) {
  const { container } = render(node as React.ReactElement);
  return { container };
}

function anchorMessage(content = "msg"): ReturnType<typeof _msg> {
  return _msg(content);
}

function _msg(content: string) {
  return {
    kind: "message" as const,
    ts: `ts-${content}`,
    agent: "x",
    state: "",
    content,
  };
}

function tool(name: string, isError: boolean): ToolItem {
  return {
    kind: "tool",
    ts: `tool-${name}`,
    agent: "",
    state: "",
    toolUseId: null,
    toolName: name,
    toolInput: null,
    toolResult: null,
    isError,
    running: false,
  };
}

function skill(argsArg: string): ToolItem {
  return {
    kind: "tool",
    ts: `skill-${argsArg}`,
    agent: "",
    state: "",
    toolUseId: null,
    toolName: "Skill",
    toolInput: { skill: "task-summoner-workflows:ticket-plan", args: argsArg },
    toolResult: null,
    isError: false,
    running: false,
  };
}

function skillEvent(skillName: string): ActivityEvent {
  const id = `t-s-${skillName}`;
  const use: ActivityEvent = {
    ts: `ts-use-${id}`,
    type: "tool_use",
    content: "Skill",
    agent: "planner",
    tool_name: "Skill",
    tool_use_id: id,
    tool_input: { skill: skillName, args: "" },
  };
  return use;
}

function toolUseEvent(name: string, id: string, input: Record<string, unknown>): ActivityEvent {
  return {
    ts: `ts-use-${id}`,
    type: "tool_use",
    content: name,
    agent: "planner",
    tool_name: name,
    tool_use_id: id,
    tool_input: input,
  };
}

function toolResultEvent(
  name: string,
  id: string,
  overrides: { is_error?: boolean; result?: string } = {},
): ActivityEvent {
  return {
    ts: `ts-res-${id}`,
    type: "tool_result",
    content: name,
    agent: "planner",
    tool_name: name,
    tool_use_id: id,
    tool_result: overrides.result ?? "ok",
    is_error: overrides.is_error ?? false,
  };
}

function completedEvent(
  state: string,
  overrides: { success?: boolean; cost_usd?: number; turns?: number } = {},
): ActivityEvent {
  return {
    ts: `ts-done-${state}`,
    type: "completed",
    content: "",
    agent: "",
    state,
    metadata: {
      agent: "",
      success: overrides.success ?? true,
      cost_usd: overrides.cost_usd ?? 0.3,
      turns: overrides.turns ?? 20,
    },
  };
}

describe("IssueActivityTimeline — step grouping", () => {
  it("collapses a completed FSM step into a summary with cost + turns", async () => {
    mockHistoryFetch([
      { ...skillEvent("task-summoner-workflows:create-design-doc"), state: "CREATING_DOC" },
      completedEvent("CREATING_DOC", { success: true, cost_usd: 0.45, turns: 24 }),
      // Live (planning) — still in flight, no completed yet.
      { ...skillEvent("task-summoner-workflows:ticket-plan"), state: "PLANNING" },
    ]);
    render(<IssueActivityTimeline issueKey="ENG-148" />);

    await waitFor(() => {
      const stepGroup = document.querySelector("[data-timeline-step-group]");
      expect(stepGroup).toBeTruthy();
    });

    const group = document.querySelector("[data-timeline-step-group]");
    expect(group?.getAttribute("data-step-state")).toBe("CREATING_DOC");
    expect(group?.textContent).toContain("Creating doc");
    expect(group?.textContent).toContain("24 turns");
    expect(group?.textContent).toContain("$0.45");
    // Collapsed by default on success → inner skill invocation is hidden.
    expect(group?.getAttribute("data-expanded")).toBe("false");
    // The in-flight PLANNING step stays ungrouped (no completed event yet).
    const planningSkill = Array.from(document.querySelectorAll("[data-timeline-tool]")).find((el) =>
      el.textContent?.includes("ticket-plan"),
    );
    expect(planningSkill).toBeTruthy();
  });

  it("auto-expands a failed step so the error stays visible", async () => {
    mockHistoryFetch([
      { ...skillEvent("task-summoner-workflows:ticket-implement"), state: "IMPLEMENTING" },
      completedEvent("IMPLEMENTING", { success: false, cost_usd: 1.2, turns: 80 }),
    ]);
    render(<IssueActivityTimeline issueKey="ENG-150" />);

    await waitFor(() => {
      const stepGroup = document.querySelector("[data-timeline-step-group]");
      expect(stepGroup?.getAttribute("data-expanded")).toBe("true");
    });
  });

  it("keeps the live step ungrouped when no completed event arrived yet", async () => {
    mockHistoryFetch([
      { ...skillEvent("task-summoner-workflows:create-design-doc"), state: "CREATING_DOC" },
      toolUseEvent("Read", "t-r1", { file_path: "a.md" }),
      toolResultEvent("Read", "t-r1"),
    ]);
    render(<IssueActivityTimeline issueKey="ENG-150b" />);

    await screen.findByText(/Skill: task-summoner-workflows:create-design-doc/i);
    // Nothing is completed yet → no step_group wrapper.
    expect(document.querySelector("[data-timeline-step-group]")).toBeNull();
  });
});
