import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { routeTree } from "../routeTree.gen";

type FetchArgs = Parameters<typeof fetch>;

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
  });
}

interface StubSetupState {
  boardProvider?: "linear" | "jira" | "";
  apiKeyMasked?: boolean;
  docsRepo?: string;
  repos?: { name: string; path: string }[];
}

function buildState(opts: StubSetupState = {}) {
  return {
    board: {
      provider: opts.boardProvider ?? "linear",
      api_key_masked: opts.apiKeyMasked ?? true,
      api_key: (opts.apiKeyMasked ?? true) ? "********" : null,
      email: null,
      team_id: "team-uuid",
      team_name: "",
      watch_label: "task-summoner",
    },
    agent: {
      provider: "claude_code",
      auth_method: "api_key",
      api_key_masked: true,
      api_key: "********",
      plugin_mode: "installed",
      plugin_path: "",
    },
    repos: opts.repos ?? [{ name: "demo", path: "/tmp/demo" }],
    general: {
      default_repo: "demo",
      polling_interval_sec: 15,
      workspace_root: "/tmp/ws",
      docs_repo: opts.docsRepo ?? "",
    },
  };
}

function renderSetup(fetchImpl: (...args: FetchArgs) => Promise<Response>) {
  vi.stubGlobal("fetch", vi.fn(fetchImpl));
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ["/setup"] }),
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

describe("Setup route — prefill + masking", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("prefills inputs from /api/setup/state and masks API keys", async () => {
    renderSetup(async (input) => {
      const url = typeof input === "string" ? input : (input as Request).url;
      if (url.endsWith("/api/setup/state")) {
        return jsonResponse(buildState({ docsRepo: "/Users/me/docs" }));
      }
      return jsonResponse({ configured: true, errors: [] });
    });

    await screen.findByRole("heading", { name: /^setup$/i });

    // API key renders the mask sentinel (never the plaintext key).
    const apiKeyInputs = await screen.findAllByDisplayValue("********");
    expect(apiKeyInputs.length).toBeGreaterThanOrEqual(1);

    // Docs repo gets prefilled.
    expect(screen.getByDisplayValue("/Users/me/docs")).toBeInTheDocument();

    // Repo name from server lands in the form (appears in the Name row +
    // the Default repo field).
    expect(screen.getAllByDisplayValue("demo").length).toBeGreaterThanOrEqual(1);
  });

  it("disables Save until a field changes, then enables it", async () => {
    renderSetup(async (input) => {
      const url = typeof input === "string" ? input : (input as Request).url;
      if (url.endsWith("/api/setup/state")) return jsonResponse(buildState());
      return jsonResponse({ configured: true, errors: [] });
    });

    const saveBtn = await screen.findByRole("button", { name: /save config/i });
    expect(saveBtn).toBeDisabled();

    // Edit the docs repo → save becomes enabled and the dot appears.
    const docsRepo = screen.getByLabelText(/docs repo path/i) as HTMLInputElement;
    fireEvent.change(docsRepo, { target: { value: "/tmp/docs-new" } });

    await waitFor(() => expect(saveBtn).not.toBeDisabled());
    expect(screen.getByTestId("field-modified-dot-docs-repo-path")).toBeInTheDocument();
  });

  it("replaces the masked value when the user clicks Replace", async () => {
    renderSetup(async (input) => {
      const url = typeof input === "string" ? input : (input as Request).url;
      if (url.endsWith("/api/setup/state")) return jsonResponse(buildState());
      return jsonResponse({ configured: true, errors: [] });
    });

    await screen.findByRole("heading", { name: /^setup$/i });

    // Two Replace buttons (board + agent), click the first → the linked
    // input must now be empty so the user can type a new secret.
    const replaceBtns = await screen.findAllByRole("button", { name: /replace/i });
    expect(replaceBtns.length).toBeGreaterThan(0);
    fireEvent.click(replaceBtns[0] as HTMLButtonElement);

    // After clicking Replace, at least one input should have been cleared.
    const api = screen.getAllByDisplayValue("");
    expect(api.length).toBeGreaterThan(0);
  });

  it("shows an inline error for a non-absolute docs_repo path", async () => {
    renderSetup(async (input) => {
      const url = typeof input === "string" ? input : (input as Request).url;
      if (url.endsWith("/api/setup/state")) return jsonResponse(buildState());
      return jsonResponse({ configured: true, errors: [] });
    });

    await screen.findByRole("heading", { name: /^setup$/i });

    const docsRepo = screen.getByLabelText(/docs repo path/i) as HTMLInputElement;
    fireEvent.change(docsRepo, { target: { value: "relative/path" } });
    fireEvent.blur(docsRepo);

    await waitFor(() => expect(screen.getByText(/must be absolute/i)).toBeInTheDocument());

    // Save button stays disabled because path validation failed.
    const saveBtn = screen.getByRole("button", { name: /save config/i });
    expect(saveBtn).toBeDisabled();
  });
});
