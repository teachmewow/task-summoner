import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
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
  it("renders markdown content when an RFC exists", async () => {
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
    await waitFor(() => {
      const h1 = document.querySelector("[data-rfc-body] h1");
      expect(h1?.textContent).toBe("Render the RFC");
    });
    // The image src gets rewritten to the API route.
    await waitFor(() => {
      const img = document.querySelector<HTMLImageElement>("[data-rfc-body] img");
      expect(img?.src).toContain("/api/rfcs/ENG-98/image/impact.png");
    });
    // "Open in editor" is visible.
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
});
