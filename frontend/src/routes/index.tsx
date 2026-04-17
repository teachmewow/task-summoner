import { createFileRoute } from "@tanstack/react-router";
import {
  Activity,
  BookOpen,
  DollarSign,
  FlaskConical,
  type LucideIcon,
  Settings,
  ShieldAlert,
  Stethoscope,
  Workflow,
} from "lucide-react";
import { Card } from "~/components/Card";

export const Route = createFileRoute("/")({
  component: Home,
});

interface CardSpec {
  icon: LucideIcon;
  title: string;
  description: string;
  href?: string;
  comingSoon?: boolean;
}

const CARDS: CardSpec[] = [
  {
    icon: Activity,
    title: "Agents Monitoring",
    description: "Live view of tickets, states, and agent events.",
    href: "/monitor",
  },
  {
    icon: Settings,
    title: "Settings",
    description: "Configure providers, agents, repos, and keys.",
    href: "/setup",
  },
  {
    icon: DollarSign,
    title: "Cost & Usage",
    description: "Token spend, per-ticket burn, and budget alerts.",
    comingSoon: true,
  },
  {
    icon: ShieldAlert,
    title: "Failure Analysis",
    description: "Recurring error patterns and retry hotspots.",
    comingSoon: true,
  },
  {
    icon: FlaskConical,
    title: "Agent Configurator",
    description: "Tune models, tools, and profiles per workflow.",
    comingSoon: true,
  },
  {
    icon: BookOpen,
    title: "Skills Editor",
    description: "Author and version the skills your agents use.",
    comingSoon: true,
  },
  {
    icon: Workflow,
    title: "Workflow Designer",
    description: "Draft state machines visually before shipping.",
    comingSoon: true,
  },
  {
    icon: Stethoscope,
    title: "Board Health",
    description: "Sync latency, stale tickets, orphaned worktrees.",
    comingSoon: true,
  },
];

function Home() {
  return (
    <section className="space-y-8">
      <header className="space-y-2">
        <p className="text-xs uppercase tracking-[0.2em] text-soul-cyan/80">Local-first SDLC</p>
        <h1 className="text-4xl font-semibold text-ghost-white">
          Summon the <span className="text-arise-violet">shadow army</span>.
        </h1>
        <p className="max-w-2xl text-soul-cyan/90">
          Pick a view below. Active cards are live; the rest are placeholders for upcoming work.
        </p>
      </header>
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {CARDS.map((card) => (
          <li key={card.title}>
            <Card {...card} />
          </li>
        ))}
      </ul>
    </section>
  );
}
