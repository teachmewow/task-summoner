import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { GateCard } from "~/components/GateCard";
import type { GateResponse } from "~/lib/gates";
import type { TicketContext } from "~/lib/issues";

/**
 * Shape the ticket cache would have after a real ``useTicket`` fetch. We
 * seed it directly via ``QueryClient.setQueryData`` so ``GateCard`` — which
 * reads metadata for artifact-visibility decisions — sees the right thing
 * without a network round-trip.
 */
function seedTicket(overrides: Partial<TicketContext> = {}): TicketContext {
  return {
    ticket_key: "ENG-95",
    state: "WAITING_DOC_REVIEW",
    created_at: "2026-04-19T00:00:00Z",
    updated_at: "2026-04-19T00:00:00Z",
    branch_name: "ENG-95-test",
    workspace_path: null,
    mr_url: null,
    retry_count: 0,
    total_cost_usd: 0,
    error: null,
    metadata: {},
    ...overrides,
  };
}

function wrap(ui: React.ReactElement, opts: { ticket?: Partial<TicketContext> } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  if (opts.ticket) {
    const ticket = seedTicket(opts.ticket);
    client.setQueryData(["tickets", ticket.ticket_key], ticket);
  }
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

  it("shows a Preview button only for artifacts the orchestrator actually drafted", () => {
    // Doc-path ticket at the doc gate: metadata.rfc_pr_url set, no plan yet.
    const { unmount } = wrap(
      <GateCard
        issueKey="ENG-95"
        gate={baseGate({ orchestrator_state: "WAITING_DOC_REVIEW" })}
        onRefresh={() => undefined}
        isRefreshing={false}
      />,
      { ticket: { metadata: { rfc_pr_url: "https://github.com/x/docs/pull/1" } } },
    );
    expect(screen.getByRole("button", { name: /preview rfc/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /preview plan/i })).not.toBeInTheDocument();
    unmount();

    // Doc-path ticket at the plan gate: both artifacts are present.
    wrap(
      <GateCard
        issueKey="ENG-95"
        gate={baseGate({
          orchestrator_state: "WAITING_PLAN_REVIEW",
          state: "in_plan_review",
          retry_skill: "ticket-plan",
        })}
        onRefresh={() => undefined}
        isRefreshing={false}
      />,
      {
        ticket: {
          metadata: {
            rfc_pr_url: "https://github.com/x/docs/pull/1",
            plan_pr_url: "https://github.com/x/plug/pull/2",
          },
        },
      },
    );
    expect(screen.getByRole("button", { name: /preview rfc/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /preview plan/i })).toBeInTheDocument();
  });

  it("hides Preview RFC on no-doc tickets (never drafted an RFC)", () => {
    // No-doc path (``Doc`` label absent upstream) — the FSM went
    // QUEUED → PLANNING directly, so ``rfc_pr_url`` was never set.
    wrap(
      <GateCard
        issueKey="ENG-162"
        gate={baseGate({
          issue_key: "ENG-162",
          orchestrator_state: "WAITING_PLAN_REVIEW",
          state: "in_plan_review",
          retry_skill: "ticket-plan",
        })}
        onRefresh={() => undefined}
        isRefreshing={false}
      />,
      {
        ticket: {
          ticket_key: "ENG-162",
          state: "WAITING_PLAN_REVIEW",
          metadata: { plan_pr_url: "https://github.com/x/plug/pull/21" },
        },
      },
    );
    expect(screen.queryByRole("button", { name: /preview rfc/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /preview plan/i })).toBeInTheDocument();
  });

  it("hides summary + action buttons when the ticket is DONE", () => {
    wrap(
      <GateCard
        issueKey="ENG-95"
        gate={baseGate({
          orchestrator_state: "DONE",
          state: "done",
          retry_skill: null,
          summary: "Implementation PR #20 ready-for-review.",
        })}
        onRefresh={() => undefined}
        isRefreshing={false}
      />,
      {
        ticket: {
          state: "DONE",
          mr_url: "https://github.com/x/plug/pull/20",
          metadata: {
            rfc_pr_url: "https://github.com/x/docs/pull/1",
            plan_pr_url: "https://github.com/x/plug/pull/20",
          },
        },
      },
    );
    // Stale "ready-for-review" summary must not leak after completion.
    expect(screen.queryByText(/ready-for-review/i)).not.toBeInTheDocument();
    // No approval actions on a terminal ticket.
    expect(screen.queryByRole("button", { name: /lgtm/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /retry with feedback/i })).not.toBeInTheDocument();
    // Preview still available so the user can re-read what shipped.
    expect(screen.getByRole("button", { name: /preview rfc/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /preview plan/i })).toBeInTheDocument();
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

  it("omits the summary paragraph entirely when no summary is present", () => {
    // Previously we rendered a dimmed "No summary available" placeholder,
    // but that added noise to the gate card — a missing summary is
    // self-evident. The paragraph simply doesn't render.
    wrap(
      <GateCard
        issueKey="ENG-95"
        gate={baseGate({ summary: null })}
        onRefresh={() => undefined}
        isRefreshing={false}
      />,
    );
    expect(document.querySelector("[data-gate-summary]")).toBeNull();
  });
});
