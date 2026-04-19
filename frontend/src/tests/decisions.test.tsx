import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DecisionsSidebar } from "~/components/DecisionsSidebar";
import type { DecisionsResponse } from "~/lib/decisions";

function wrap(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function mockFetch(body: DecisionsResponse | Record<string, unknown>, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify(body), {
          status,
          headers: { "Content-Type": "application/json" },
        }),
    ),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("DecisionsSidebar", () => {
  it("shows empty state + template link when no decisions exist", async () => {
    mockFetch({
      ok: true,
      configured: true,
      docs_repo: "/tmp/docs",
      template_readme_url: "https://example.com/template",
      decisions: [],
      reason: null,
    });
    wrap(<DecisionsSidebar />);
    await screen.findByText(/No decisions yet/i);
    expect(screen.getByRole("link", { name: /Template README/i })).toHaveAttribute(
      "href",
      "https://example.com/template",
    );
  });

  it("renders decisions sorted server-side and shows tags", async () => {
    mockFetch({
      ok: true,
      configured: true,
      docs_repo: "/tmp/docs",
      template_readme_url: "https://example.com/template",
      decisions: [
        {
          filename: "2026-04-harness-flow.md",
          path: "/tmp/docs/decisions/2026-04-harness-flow.md",
          relative_path: "decisions/2026-04-harness-flow.md",
          title: "Harness flow gap analysis",
          summary: "Audit the SDLC against existing skills.",
          tags: ["architecture", "mvp"],
          committed_at: "2026-04-18T00:00:00+00:00",
        },
        {
          filename: "2026-04-architecture-dsl.md",
          path: "/tmp/docs/decisions/2026-04-architecture-dsl.md",
          relative_path: "decisions/2026-04-architecture-dsl.md",
          title: "Architecture DSL",
          summary: "Pick a DSL to describe C4 diagrams.",
          tags: ["architecture"],
          committed_at: "2026-04-17T00:00:00+00:00",
        },
      ],
      reason: null,
    });

    wrap(<DecisionsSidebar />);
    await waitFor(() => {
      expect(screen.getByText(/Harness flow gap analysis/i)).toBeInTheDocument();
      expect(screen.getByText(/Architecture DSL/i)).toBeInTheDocument();
    });
    // Tag filter buttons show both tags de-duplicated; "architecture" is shared
    // so we see it in the filter bar + inside each decision's tag pills.
    expect(screen.getAllByText("architecture").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("mvp").length).toBeGreaterThanOrEqual(1);
  });

  it("shows the 'configure docs_repo' CTA when unconfigured", async () => {
    mockFetch({
      ok: true,
      configured: false,
      docs_repo: null,
      template_readme_url: "https://example.com/template",
      decisions: [],
      reason: "docs_repo is not configured.",
    });
    wrap(<DecisionsSidebar />);
    await screen.findByText(/docs_repo is not configured/i);
    expect(screen.getByRole("link", { name: /Use the template/i })).toBeInTheDocument();
  });
});
