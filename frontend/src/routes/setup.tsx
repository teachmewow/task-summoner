import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/setup")({
  component: Setup,
});

function Setup() {
  return (
    <section className="space-y-3">
      <h1 className="text-2xl font-semibold text-ghost-white">Setup</h1>
      <p className="text-soul-cyan/90">Placeholder — provider + agent wizard lands in ENG-69.</p>
    </section>
  );
}
