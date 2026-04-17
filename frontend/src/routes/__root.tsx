import { Link, Outlet, createRootRoute } from "@tanstack/react-router";

export const Route = createRootRoute({
  component: RootLayout,
});

function RootLayout() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-arise-ink px-6 py-4">
        <nav className="flex gap-6 text-sm">
          <Link to="/" className="text-arise-violet hover:underline">
            Home
          </Link>
          <Link to="/monitor" className="text-arise-violet hover:underline">
            Monitor
          </Link>
          <Link to="/setup" className="text-arise-violet hover:underline">
            Setup
          </Link>
        </nav>
      </header>
      <main className="p-8">
        <Outlet />
      </main>
    </div>
  );
}
