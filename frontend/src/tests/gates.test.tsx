import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { GateCard } from "~/components/GateCard";
import type { GateResponse } from "~/lib/gates";

function wrap(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function baseGate(overrides: Partial<GateResponse> = {}): GateResponse {
  return {
    issue_key: "ENG-95",
    state: "in_doc_review",
    active_pr: {
      url: "https://github.com/teachmewow/tmw-docs/pull/42",
      number: 42,
      state: "OPEN",
      is_draft: false,
      head_branch: "rfc/eng-95",
    },
    retry_skill: "address-doc-feedback",
    reason: "",
    related_prs: [],
    linear_status_type: "started",
    linear_status_name: "In Progress",
    summary: "RFC drafted covering storage + rollout; open for review.",
    orchestrator_state: "WAITING_DOC_REVIEW",
    orchestrator_pr_url: null,
    ...overrides,
  };
}

describe("GateCard", () => {
  it("renders the gate chip label for the current state", () => {
    wrap(
      <GateCard
        issueKey="ENG-95"
        gate={baseGate()}
        onRefresh={() => undefined}
        isRefreshing={false}
      />,
    );
    expect(screen.getByText("In doc review")).toBeInTheDocument();
    expect(screen.getByText(/Active PR/i)).toBeInTheDocument();
  });

  it("shows lgtm + retry buttons for reviewable states", () => {
    wrap(
      <GateCard
        issueKey="ENG-95"
        gate={baseGate()}
        onRefresh={() => undefined}
        isRefreshing={false}
      />,
    );
    expect(screen.getByRole("button", { name: /lgtm/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry with feedback/i })).toBeInTheDocument();
    expect(screen.getByText(/address-doc-feedback/)).toBeInTheDocument();
  });

  it("hides action buttons for non-reviewable states (e.g. writing_doc)", () => {
    wrap(
      <GateCard
        issueKey="ENG-95"
        gate={baseGate({ state: "writing_doc", active_pr: null, retry_skill: null })}
        onRefresh={() => undefined}
        isRefreshing={false}
      />,
    );
    expect(screen.queryByRole("button", { name: /lgtm/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /retry with feedback/i })).toBeNull();
  });

  it("renders a manual-check banner with the reason", () => {
    wrap(
      <GateCard
        issueKey="ENG-95"
        gate={baseGate({
          state: "manual_check",
          reason: "Code PR is merged but Linear state is 'In Review'.",
          active_pr: null,
          retry_skill: null,
        })}
        onRefresh={() => undefined}
        isRefreshing={false}
      />,
    );
    expect(screen.getByText(/Manual check needed/i)).toBeInTheDocument();
    expect(screen.getByText(/Linear state/i)).toBeInTheDocument();
  });

  it("fires onRefresh when the refresh button is clicked", () => {
    const onRefresh = vi.fn();
    wrap(
      <GateCard issueKey="ENG-95" gate={baseGate()} onRefresh={onRefresh} isRefreshing={false} />,
    );
    fireEvent.click(screen.getByTitle(/refresh pr state/i));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("opens the request-changes modal when retry button is clicked", () => {
    wrap(
      <GateCard
        issueKey="ENG-95"
        gate={baseGate()}
        onRefresh={() => undefined}
        isRefreshing={false}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /retry with feedback/i }));
    expect(screen.getByPlaceholderText(/needs to change/i)).toBeInTheDocument();
  });

  it("renders the skill-emitted summary prominently", () => {
    wrap(
      <GateCard
        issueKey="ENG-95"
        gate={baseGate({ summary: "Plan committed; 3 files, ~50 LOC estimated." })}
        onRefresh={() => undefined}
        isRefreshing={false}
      />,
    );
    const el = screen.getByText(/Plan committed; 3 files/);
    expect(el).toBeInTheDocument();
    expect(el).toHaveAttribute("data-gate-summary");
  });

  it("renders a dimmed fallback when summary is missing", () => {
    wrap(
      <GateCard
        issueKey="ENG-95"
        gate={baseGate({ summary: null })}
        onRefresh={() => undefined}
        isRefreshing={false}
      />,
    );
    const el = screen.getByText(/No summary available/i);
    expect(el).toBeInTheDocument();
    expect(el).toHaveAttribute("data-gate-summary", "missing");
  });
});
