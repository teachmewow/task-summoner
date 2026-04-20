import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RfcPreviewModal } from "~/components/RfcPreviewModal";
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

describe("RfcPreviewModal", () => {
  it("renders nothing when closed, even if the hook has data", () => {
    mockFetch({
      ok: true,
      exists: true,
      issue_key: "ENG-98",
      title: "Render the RFC",
      content: "# Render the RFC\n\nHello.",
      readme_path: "/tmp/r.md",
      images: [],
      reason: null,
    });
    wrap(<RfcPreviewModal issueKey="ENG-98" open={false} onClose={() => undefined} />);
    expect(document.querySelector("[data-markdown-preview-modal]")).toBeNull();
  });

  it("renders markdown body when open with an existing RFC (H1 stripped)", async () => {
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
    wrap(<RfcPreviewModal issueKey="ENG-98" open={true} onClose={() => undefined} />);

    // Modal header owns the title (``<h2>``); the markdown body renders
    // below it with the leading ``# Render the RFC`` stripped so the
    // title isn't displayed twice.
    await waitFor(() => {
      const body = document.querySelector("[data-markdown-preview-body='rfc']");
      expect(body?.textContent).toMatch(/markdown/);
    });
    expect(document.querySelector("[data-markdown-preview-body='rfc'] h1")).toBeNull();
    // Image rewriting still happens via the postRender callback.
    await waitFor(() => {
      const img = document.querySelector<HTMLImageElement>(
        "[data-markdown-preview-body='rfc'] img",
      );
      expect(img?.src).toContain("/api/rfcs/ENG-98/image/impact.png");
    });
    // Open in editor CTA lives in the modal header.
    expect(screen.getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
  });

  it("shows the 'not drafted yet' hint when the RFC does not exist", async () => {
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
    wrap(<RfcPreviewModal issueKey="ENG-99" open={true} onClose={() => undefined} />);
    await screen.findByText(/No rfc drafted yet for ENG-99/i);
  });

  it("surfaces the reason when docs_repo is not configured", async () => {
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
    wrap(<RfcPreviewModal issueKey="ENG-98" open={true} onClose={() => undefined} />);
    await screen.findByText(/docs_repo is not configured/i);
  });
});
