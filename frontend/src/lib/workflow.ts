import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./api";

export interface WorkflowNode {
  id: string;
  label: string;
  kind: "start" | "agent" | "approval" | "terminal" | "other";
  x: number;
  y: number;
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  trigger: string;
}

export interface WorkflowResponse {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}

export interface WorkflowLiveCount {
  state: string;
  count: number;
}

export interface WorkflowLiveResponse {
  total_tickets: number;
  counts: WorkflowLiveCount[];
}

export function useWorkflow() {
  return useQuery({
    queryKey: ["workflow"] as const,
    queryFn: () => apiFetch<WorkflowResponse>("/api/workflow"),
  });
}

export function useWorkflowLive() {
  return useQuery({
    queryKey: ["workflow", "live"] as const,
    queryFn: () => apiFetch<WorkflowLiveResponse>("/api/workflow/live"),
    refetchInterval: 5_000,
  });
}
