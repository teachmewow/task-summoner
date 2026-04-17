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
  it("renders 8 cards: 3 active, 5 coming-soon", async () => {
    renderAt("/");
    await screen.findByText(/shadow army/i);

    const cards = document.querySelectorAll("[data-card]");
    expect(cards).toHaveLength(8);

    const active = document.querySelectorAll('[data-card][data-kind="active"]');
    const placeholders = document.querySelectorAll('[data-card][data-kind="placeholder"]');
    expect(active).toHaveLength(3);
    expect(placeholders).toHaveLength(5);

    expect(screen.getByText("Agents Monitoring")).toBeInTheDocument();
    expect(screen.getByText("Settings")).toBeInTheDocument();
    expect(screen.getByText("Cost & Usage")).toBeInTheDocument();
    expect(screen.getAllByText(/coming soon/i)).toHaveLength(5);
  });
});
