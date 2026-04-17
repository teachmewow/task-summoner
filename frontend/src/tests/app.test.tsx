import { RouterProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { routeTree } from "../routeTree.gen";

function renderAt(path: string) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [path] }),
  });
  return render(<RouterProvider router={router} />);
}

describe("Home card grid", () => {
  it("renders 8 cards: 2 active, 6 coming-soon", async () => {
    renderAt("/");
    await screen.findByText(/shadow army/i);

    const cards = document.querySelectorAll("[data-card]");
    expect(cards).toHaveLength(8);

    const active = document.querySelectorAll('[data-card][data-kind="active"]');
    const placeholders = document.querySelectorAll('[data-card][data-kind="placeholder"]');
    expect(active).toHaveLength(2);
    expect(placeholders).toHaveLength(6);

    expect(screen.getByText("Agents Monitoring")).toBeInTheDocument();
    expect(screen.getByText("Settings")).toBeInTheDocument();
    expect(screen.getAllByText(/coming soon/i)).toHaveLength(6);
  });
});
