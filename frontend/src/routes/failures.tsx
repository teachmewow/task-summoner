import { createFileRoute } from "@tanstack/react-router";
import { RefreshCcw } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  type FailedTicket,
  type FailureByCategory,
  type FailureByPhase,
  useFailureSummary,
  useRetryTicket,
} from "~/lib/failures";

export const Route = createFileRoute("/failures")({
  component: Failures,
});

const VIOLET = "#A855F7";
const VIOLET_BRIGHT = "#C084FC";
const EMBER = "#F87171";
const AMBER = "#FBBF24";
const SHADOW = "#3D1B6B";
const INK = "#E9D5FF";
const SPIRIT = "#C4B5FD";

function Failures() {
  const { data, isLoading, isError } = useFailureSummary();
  const retry = useRetryTicket();

  if (isLoading) return <p className="text-soul-cyan/80">Loading failures…</p>;
  if (isError || !data) return <p className="text-ember-red">Failed to load failures.</p>;

  return (
    <section className="space-y-8">
      <header className="space-y-1">
        <h1 className="text-3xl font-semibold text-ghost-white">Failure Analysis</h1>
        <p className="text-soul-cyan/80">
          FAILED tickets, retry patterns, and quarantine state — polls every 10s.
        </p>
      </header>

      <KpiRow total={data.total_failed} quarantined={data.quarantined} healthy={data.healthy} />

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="By phase">
          <ByPhase phases={data.by_phase} />
        </Panel>
        <Panel title="By category">
          <ByCategory categories={data.by_category} />
        </Panel>
      </div>

      <Panel title={`Failed tickets (${data.tickets.length})`}>
        <TicketList
          tickets={data.tickets}
          onRetry={(key) => retry.mutate(key)}
          retrying={retry.isPending ? retry.variables : null}
        />
      </Panel>
    </section>
  );
}

function KpiRow({
  total,
  quarantined,
  healthy,
}: {
  total: number;
  quarantined: number;
  healthy: number;
}) {
  const items = [
    { label: "Total failed", value: total, tint: total > 0 ? EMBER : INK },
    { label: "Quarantined", value: quarantined, tint: quarantined > 0 ? AMBER : INK },
    { label: "Healthy", value: healthy, tint: INK },
  ];
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {items.map((it) => (
        <div
          key={it.label}
          className="rounded-lg border border-shadow-purple/60 bg-void-800/70 p-5"
        >
          <p className="text-xs uppercase tracking-wider text-soul-cyan/70">{it.label}</p>
          <p className="mt-1 text-2xl font-semibold" style={{ color: it.tint }}>
            {it.value}
          </p>
        </div>
      ))}
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-shadow-purple/60 bg-void-800/70 p-5">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-arise-violet-bright">
        {title}
      </h2>
      {children}
    </section>
  );
}

function ByPhase({ phases }: { phases: FailureByPhase[] }) {
  if (phases.length === 0) return <Empty label="No failures yet." />;
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={phases} margin={{ top: 5, right: 8, bottom: 0, left: -16 }}>
        <CartesianGrid stroke={SHADOW} strokeOpacity={0.4} vertical={false} />
        <XAxis dataKey="phase" stroke={SPIRIT} tick={{ fill: SPIRIT, fontSize: 11 }} />
        <YAxis stroke={SPIRIT} tick={{ fill: SPIRIT, fontSize: 11 }} allowDecimals={false} />
        <Tooltip
          contentStyle={{
            background: "#0F0A1F",
            border: `1px solid ${SHADOW}`,
            borderRadius: 6,
            color: INK,
          }}
        />
        <Bar dataKey="count" fill={EMBER} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function ByCategory({ categories }: { categories: FailureByCategory[] }) {
  if (categories.length === 0) return <Empty label="No failures yet." />;
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={categories} margin={{ top: 5, right: 8, bottom: 0, left: -16 }}>
        <CartesianGrid stroke={SHADOW} strokeOpacity={0.4} vertical={false} />
        <XAxis dataKey="category" stroke={SPIRIT} tick={{ fill: SPIRIT, fontSize: 11 }} />
        <YAxis stroke={SPIRIT} tick={{ fill: SPIRIT, fontSize: 11 }} allowDecimals={false} />
        <Tooltip
          contentStyle={{
            background: "#0F0A1F",
            border: `1px solid ${SHADOW}`,
            borderRadius: 6,
            color: INK,
          }}
          formatter={(v: unknown, _name: unknown, ctx: { payload?: FailureByCategory }) => [
            `${Number(v)} · ${ctx.payload?.sample_message ?? ""}`,
            "Count",
          ]}
        />
        <Bar dataKey="count" fill={VIOLET} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function TicketList({
  tickets,
  onRetry,
  retrying,
}: {
  tickets: FailedTicket[];
  onRetry: (key: string) => void;
  retrying: string | null | undefined;
}) {
  if (tickets.length === 0) {
    return <Empty label="Everything is healthy. No failed tickets." />;
  }
  return (
    <ul className="divide-y divide-shadow-purple/30">
      {tickets.map((t) => (
        <li key={t.ticket_key} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-start">
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-ghost-white">{t.ticket_key}</span>
              <CategoryPill category={t.category} />
              <PhasePill phase={t.last_phase} />
              {t.quarantined ? (
                <span className="rounded-full border border-amber-flame/50 bg-amber-flame/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-amber-flame">
                  Quarantined
                </span>
              ) : null}
            </div>
            <p className="break-words text-sm text-soul-cyan/80">{t.error || "—"}</p>
            <p className="text-xs text-soul-cyan/60">
              retries: {t.retry_count} · spent: ${t.total_cost_usd.toFixed(2)} · updated{" "}
              {t.updated_at.slice(0, 19).replace("T", " ")}
            </p>
          </div>
          <button
            type="button"
            onClick={() => onRetry(t.ticket_key)}
            disabled={retrying === t.ticket_key}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-shadow-purple/60 bg-void-900/60 px-3 py-1.5 text-xs font-medium text-soul-cyan transition hover:border-arise-violet/70 hover:text-ghost-white disabled:opacity-50"
          >
            <RefreshCcw size={12} strokeWidth={2} />
            {retrying === t.ticket_key ? "Queuing…" : "Retry"}
          </button>
        </li>
      ))}
    </ul>
  );
}

function CategoryPill({ category }: { category: string }) {
  const tint =
    category === "board_not_found" ? AMBER : category === "timeout" ? EMBER : VIOLET_BRIGHT;
  return (
    <span
      className="rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider"
      style={{ color: tint, borderColor: `${tint}55`, background: `${tint}10` }}
    >
      {category}
    </span>
  );
}

function PhasePill({ phase }: { phase: string }) {
  return (
    <span className="rounded-full border border-shadow-purple/50 bg-void-900/60 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-soul-cyan/80">
      {phase}
    </span>
  );
}

function Empty({ label }: { label: string }) {
  return <p className="text-sm text-soul-cyan/60">{label}</p>;
}
