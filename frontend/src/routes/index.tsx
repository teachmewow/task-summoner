import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/")({
  component: Home,
});

function Home() {
  return (
    <section>
      <h1 className="text-3xl font-semibold text-arise-violet">Task Summoner</h1>
      <p className="mt-2 text-white/70">Hello world — React + TanStack Router scaffold is live.</p>
    </section>
  );
}
