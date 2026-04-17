import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/")({
  component: Home,
});

function Home() {
  return (
    <section className="space-y-4">
      <p className="text-xs uppercase tracking-[0.2em] text-soul-cyan/80">Local-first SDLC</p>
      <h1 className="text-4xl font-semibold text-ghost-white">
        Summon the <span className="text-arise-violet">shadow army</span>.
      </h1>
      <p className="max-w-xl text-soul-cyan/90">
        Task Summoner runs on your machine, uses your CLI billing, and gates every phase. Pick a
        ticket, the agents rise.
      </p>
      <div className="flex gap-3 pt-2">
        <CtaCard title="Monitor agents" href="/monitor" />
        <CtaCard title="Configure" href="/setup" />
      </div>
    </section>
  );
}

function CtaCard({ title, href }: { title: string; href: string }) {
  return (
    <a
      href={href}
      className="glow-violet rounded-md border border-shadow-purple bg-void-800 px-5 py-3 text-sm font-medium text-ghost-white transition-colors hover:bg-void-700"
    >
      {title}
    </a>
  );
}
