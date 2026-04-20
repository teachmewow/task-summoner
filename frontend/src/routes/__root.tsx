import { Link, Outlet, createRootRoute } from "@tanstack/react-router";
import type { ReactNode } from "react";
import logoUrl from "~/assets/logo.svg";
import { ArcaneBackground } from "~/components/ArcaneBackground";
import { SetupBanner } from "~/components/SetupBanner";

export const Route = createRootRoute({
  component: RootLayout,
});

function RootLayout() {
  return (
    <div className="min-h-screen">
      <ArcaneBackground />
      <SetupBanner />
      <header className="border-b border-rune-line-strong bg-obsidian-raised/60 backdrop-blur-sm">
        <div className="mx-auto flex max-w-6xl items-center gap-8 px-6 py-4">
          <Link to="/" className="flex items-center gap-3">
            <img src={logoUrl} alt="" className="h-8 w-8" />
            <span className="text-lg font-semibold tracking-wide text-ghost">Task Summoner</span>
          </Link>
          <nav className="flex gap-5 text-sm">
            <NavLink to="/">Home</NavLink>
            <NavLink to="/monitor">Monitor</NavLink>
            <NavLink to="/setup">Setup</NavLink>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-10">
        <Outlet />
      </main>
    </div>
  );
}

function NavLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link
      to={to}
      className="text-ghost-dim transition-colors hover:text-arcane"
      activeProps={{ className: "text-arcane" }}
    >
      {children}
    </Link>
  );
}
