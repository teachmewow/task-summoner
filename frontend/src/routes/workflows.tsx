import {
  Background,
  BackgroundVariant,
  type Edge,
  Handle,
  type Node,
  Position,
  ReactFlow,
  ReactFlowProvider,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { createFileRoute } from "@tanstack/react-router";
import { useMemo } from "react";
import type { WorkflowNode } from "~/lib/workflow";
import { useWorkflow, useWorkflowLive } from "~/lib/workflow";

export const Route = createFileRoute("/workflows")({
  component: Workflows,
});

type StateNodeData = {
  label: string;
  kind: WorkflowNode["kind"];
  count: number;
};

const KIND_STYLES: Record<WorkflowNode["kind"], { accent: string; bg: string; border: string }> = {
  start: {
    accent: "#C4B5FD",
    bg: "rgba(26, 15, 46, 0.9)",
    border: "rgba(196, 181, 253, 0.55)",
  },
  agent: {
    accent: "#A855F7",
    bg: "rgba(26, 15, 46, 0.9)",
    border: "rgba(168, 85, 247, 0.55)",
  },
  approval: {
    accent: "#FBBF24",
    bg: "rgba(26, 15, 46, 0.9)",
    border: "rgba(251, 191, 36, 0.55)",
  },
  terminal: {
    accent: "#34D399",
    bg: "rgba(15, 10, 31, 0.9)",
    border: "rgba(52, 211, 153, 0.55)",
  },
  other: {
    accent: "#C4B5FD",
    bg: "rgba(26, 15, 46, 0.9)",
    border: "rgba(61, 27, 107, 0.6)",
  },
};

function StateNode({ data }: { data: StateNodeData }) {
  const style = KIND_STYLES[data.kind];
  const isTerminalFailed = data.kind === "terminal" && data.label === "FAILED";
  const accent = isTerminalFailed ? "#F87171" : style.accent;
  return (
    <div
      style={{
        background: style.bg,
        borderColor: isTerminalFailed ? "rgba(248, 113, 113, 0.6)" : style.border,
        boxShadow: `0 0 0 1px ${accent}22, 0 10px 30px rgba(10,5,20,0.45)`,
      }}
      className="min-w-[170px] rounded-md border px-3 py-2 text-xs"
    >
      <Handle type="target" position={Position.Left} style={{ background: accent }} />
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-semibold tracking-wide text-ghost">{data.label}</span>
        {data.count > 0 ? (
          <span
            className="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold"
            style={{ background: `${accent}22`, color: accent }}
          >
            {data.count}
          </span>
        ) : null}
      </div>
      <div className="mt-1 text-[10px] uppercase tracking-[0.14em]" style={{ color: accent }}>
        {data.kind}
      </div>
      <Handle type="source" position={Position.Right} style={{ background: accent }} />
    </div>
  );
}

const NODE_TYPES = { state: StateNode } as const;

function Workflows() {
  const workflow = useWorkflow();
  const live = useWorkflowLive();

  const counts = useMemo(() => {
    const map: Record<string, number> = {};
    for (const c of live.data?.counts ?? []) map[c.state] = c.count;
    return map;
  }, [live.data]);

  const nodes = useMemo<Node<StateNodeData>[]>(() => {
    if (!workflow.data) return [];
    return workflow.data.nodes.map((n) => ({
      id: n.id,
      type: "state",
      position: { x: n.x, y: n.y },
      data: { label: n.label, kind: n.kind, count: counts[n.id] ?? 0 },
      draggable: true,
    }));
  }, [workflow.data, counts]);

  const edges = useMemo<Edge[]>(() => {
    if (!workflow.data) return [];
    return workflow.data.edges.map((e) => {
      const isFailure =
        e.target === "FAILED" || e.trigger.includes("fail") || e.trigger === "retry";
      return {
        id: e.id,
        source: e.source,
        target: e.target,
        label: e.trigger,
        animated: (counts[e.source] ?? 0) > 0,
        style: {
          stroke: isFailure ? "#F87171AA" : "#A855F7AA",
          strokeWidth: 1.5,
        },
        labelStyle: { fill: "#C4B5FD", fontSize: 10 },
        labelBgStyle: { fill: "#0F0A1F", stroke: "#3D1B6B" },
        labelBgPadding: [3, 2],
      } satisfies Edge;
    });
  }, [workflow.data, counts]);

  if (workflow.isLoading) return <p className="text-ghost/80">Loading FSM…</p>;
  if (workflow.isError || !workflow.data)
    return <p className="text-blood">Failed to load workflow.</p>;

  return (
    <section className="space-y-4">
      <header className="flex items-baseline justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-3xl font-semibold text-ghost">Workflow Designer</h1>
          <p className="text-ghost/80">
            Deterministic FSM · {nodes.length} states · {edges.length} transitions
            {live.data ? ` · ${live.data.total_tickets} tracked tickets` : ""}
          </p>
        </div>
        <Legend />
      </header>

      <div
        style={{ height: 620 }}
        className="overflow-hidden rounded-lg border border-rune-line-strong bg-vault"
      >
        <ReactFlowProvider>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={NODE_TYPES}
            fitView
            fitViewOptions={{ padding: 0.15 }}
            proOptions={{ hideAttribution: true }}
            nodesDraggable={true}
            nodesConnectable={false}
            elementsSelectable={false}
          >
            <Background
              color="rgba(168, 85, 247, 0.12)"
              gap={24}
              variant={BackgroundVariant.Dots}
            />
          </ReactFlow>
        </ReactFlowProvider>
      </div>
    </section>
  );
}

function Legend() {
  const items: { kind: WorkflowNode["kind"]; label: string }[] = [
    { kind: "start", label: "Start" },
    { kind: "agent", label: "Agent" },
    { kind: "approval", label: "Approval" },
    { kind: "terminal", label: "Terminal" },
  ];
  return (
    <div className="flex flex-wrap gap-2 text-[10px] uppercase tracking-wider">
      {items.map((it) => {
        const accent = KIND_STYLES[it.kind].accent;
        return (
          <span
            key={it.kind}
            className="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-ghost/80"
            style={{ borderColor: `${accent}55` }}
          >
            <span className="h-2 w-2 rounded-full" style={{ background: accent }} />
            {it.label}
          </span>
        );
      })}
    </div>
  );
}
