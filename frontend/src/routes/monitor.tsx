import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/monitor")({
  component: Monitor,
});

function Monitor() {
  return (
    <section>
      <h1 className="text-2xl font-semibold">Agents Monitoring</h1>
      <p className="mt-2 text-white/70">Placeholder — port dashboard here in ENG-68.</p>
    </section>
  );
}
