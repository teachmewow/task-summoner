import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { routeTree } from "../routeTree.gen";

function renderAt(path: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify({ configured: true, errors: [] }), {
          headers: { "Content-Type": "application/json" },
        }),
    ),
  );
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [path] }),
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

describe("Home card grid", () => {
  it("renders 8 active cards (all placeholders shipped)", async () => {
    renderAt("/");
    await screen.findByText(/shadow army/i);

    const cards = document.querySelectorAll("[data-card]");
    expect(cards).toHaveLength(8);

    const active = document.querySelectorAll('[data-card][data-kind="active"]');
    const placeholders = document.querySelectorAll('[data-card][data-kind="placeholder"]');
    expect(active).toHaveLength(8);
    expect(placeholders).toHaveLength(0);

    expect(screen.getByText("Board Health")).toBeInTheDocument();
    expect(screen.queryByText(/coming soon/i)).toBeNull();
  });
});
