import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RfcPanel } from "~/components/RfcPanel";
import type { RfcResponse } from "~/lib/rfcs";

function wrap(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function mockFetch(body: RfcResponse) {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify(body), {
          headers: { "Content-Type": "application/json" },
        }),
    ),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("RfcPanel", () => {
  it("renders markdown content after expanding the panel", async () => {
    mockFetch({
      ok: true,
      exists: true,
      issue_key: "ENG-98",
      title: "Render the RFC",
      content:
        "# Render the RFC\n\nDescribes how **markdown** renders with an ![impact](impact.png).",
      readme_path: "/tmp/docs/rfcs/ENG-98/README.md",
      images: ["impact.png"],
      reason: null,
    });
    wrap(<RfcPanel issueKey="ENG-98" />);
    // Collapsed by default — the header shows the title, the body is hidden.
    await screen.findByText(/click to expand/i);
    expect(document.querySelector("[data-rfc-body]")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /click to expand/i }));

    await waitFor(() => {
      const h1 = document.querySelector("[data-rfc-body] h1");
      expect(h1?.textContent).toBe("Render the RFC");
    });
    await waitFor(() => {
      const img = document.querySelector<HTMLImageElement>("[data-rfc-body] img");
      expect(img?.src).toContain("/api/rfcs/ENG-98/image/impact.png");
    });
    expect(screen.getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
  });

  it("renders the empty state + summon CTA when no RFC exists", async () => {
    mockFetch({
      ok: true,
      exists: false,
      issue_key: "ENG-99",
      title: "",
      content: "",
      readme_path: "",
      images: [],
      reason: null,
    });
    const onSummon = vi.fn();
    wrap(<RfcPanel issueKey="ENG-99" onSummonCreateDesignDoc={onSummon} />);
    await screen.findByText(/No RFC found/i);
    expect(screen.getByRole("button", { name: /summon create-design-doc/i })).toBeInTheDocument();
  });

  it("surfaces a reason when docs_repo is not configured", async () => {
    mockFetch({
      ok: false,
      exists: false,
      issue_key: "ENG-98",
      title: "",
      content: "",
      readme_path: "",
      images: [],
      reason: "docs_repo is not configured.",
    });
    wrap(<RfcPanel issueKey="ENG-98" />);
    await screen.findByText(/docs_repo is not configured/i);
  });

  it("shows the drafting message while the orchestrator is in CREATING_DOC", async () => {
    mockFetch({
      ok: true,
      exists: false,
      issue_key: "ENG-121",
      title: "",
      content: "",
      readme_path: "",
      images: [],
      reason: null,
    });
    wrap(<RfcPanel issueKey="ENG-121" orchestratorState="CREATING_DOC" />);
    await screen.findByText(/agent is drafting the rfc/i);
    // The misleading "Run /create-design-doc" CTA must not render.
    expect(document.body.textContent).not.toMatch(/\/create-design-doc/);
  });

  it("does not tell the user to run /create-design-doc when no orchestrator state is known", async () => {
    mockFetch({
      ok: true,
      exists: false,
      issue_key: "ENG-200",
      title: "",
      content: "",
      readme_path: "",
      images: [],
      reason: null,
    });
    wrap(<RfcPanel issueKey="ENG-200" />);
    await screen.findByText(/no rfc found/i);
    expect(document.body.textContent).not.toMatch(/\/create-design-doc/);
  });
});
