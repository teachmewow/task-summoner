import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/setup")({
  component: Setup,
});

function Setup() {
  return (
    <section>
      <h1 className="text-2xl font-semibold">Setup</h1>
      <p className="mt-2 text-white/70">Placeholder — port config wizard here in ENG-69.</p>
    </section>
  );
}
