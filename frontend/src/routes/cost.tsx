import { createFileRoute } from "@tanstack/react-router";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  type BudgetStatus,
  type CostByDay,
  type CostByProfile,
  type CostByTicket,
  type CostSummary,
  type TurnsBucket,
  useCostSummary,
} from "~/lib/cost";

export const Route = createFileRoute("/cost")({
  component: Cost,
});

// Hex palette for Recharts SVG (tailwind classes don't apply inside
// chart primitives). Keep in sync with the arcane theme in styles.css.
const ARCANE = "#36e0d0";
const ARCANE_BRIGHT = "#7beee4";
const BLOOD = "#ff5577";
const MANA = "#7ae582";
const RUNE_LINE = "#2b3570";
const GHOST = "#eef2ff";
const GHOST_DIM = "#bcc5e6";

function Cost() {
  const { data, isLoading, isError } = useCostSummary();

  if (isLoading) {
    return <p className="text-ghost/80">Loading cost summary…</p>;
  }
  if (isError || !data) {
    return <p className="text-blood">Failed to load cost summary.</p>;
  }

  return (
    <section className="space-y-8">
      <header className="space-y-1">
        <h1 className="text-3xl font-semibold text-ghost">Cost & Usage</h1>
        <p className="text-ghost/80">Spend across all tickets — updates every 10s.</p>
      </header>

      <KpiRow data={data} />
      <BudgetCard budget={data.budget} />

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Spend over time">
          <SpendOverTime days={data.by_day} />
        </Panel>
        <Panel title="By agent profile">
          <ByProfile profiles={data.by_profile} />
        </Panel>
        <Panel title="Turns per run">
          <TurnsHistogram buckets={data.turns_histogram} />
        </Panel>
        <Panel title="Top tickets">
          <CostTable tickets={data.by_ticket.slice(0, 8)} />
        </Panel>
      </div>
    </section>
  );
}

function KpiRow({ data }: { data: CostSummary }) {
  const items = [
    { label: "Total", value: `$${data.total_cost_usd.toFixed(2)}` },
    { label: "This month", value: `$${data.budget.month_spent_usd.toFixed(2)}` },
    { label: "Avg / ticket", value: `$${data.avg_per_ticket_usd.toFixed(2)}` },
    { label: "Runs", value: String(data.run_count) },
  ];
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {items.map((it) => (
        <div key={it.label} className="rounded-lg border border-rune-line-strong bg-vault-soft p-5">
          <p className="text-xs uppercase tracking-wider text-ghost-dim">{it.label}</p>
          <p className="mt-1 text-2xl font-semibold text-ghost">{it.value}</p>
        </div>
      ))}
    </div>
  );
}

function BudgetCard({ budget }: { budget: BudgetStatus }) {
  if (budget.monthly_budget_usd == null) {
    return (
      <div className="rounded-lg border border-rune-line-strong bg-vault-soft p-5 text-sm text-ghost/80">
        No <code className="text-arcane">monthly_budget_usd</code> set — add it to{" "}
        <code>config.yaml</code> to see budget burndown.
      </div>
    );
  }
  const pct = budget.pct_used ?? 0;
  const clamped = Math.min(100, Math.max(0, pct));
  const warn = pct > 80;
  const over = pct >= 100;
  const color = over ? BLOOD : warn ? "#ff8a5b" : MANA;

  return (
    <div className="space-y-3 rounded-lg border border-rune-line-strong bg-vault-soft p-5">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-arcane">
          Monthly budget
        </h2>
        <span className="text-sm text-ghost/80">
          ${budget.month_spent_usd.toFixed(2)} / ${budget.monthly_budget_usd.toFixed(2)}
          {budget.remaining_usd != null ? (
            <>
              {" · "}
              <span className={over ? "text-blood" : "text-ghost"}>
                ${budget.remaining_usd.toFixed(2)} left
              </span>
            </>
          ) : null}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-vault">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${clamped}%`, background: color }}
        />
      </div>
      <p className="text-xs text-ghost-dim">{pct.toFixed(1)}% of budget used.</p>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-rune-line-strong bg-vault-soft p-5">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-arcane">{title}</h2>
      {children}
    </section>
  );
}

function SpendOverTime({ days }: { days: CostByDay[] }) {
  if (days.length === 0) return <Empty label="No runs recorded yet." />;
  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={days} margin={{ top: 5, right: 8, bottom: 0, left: -16 }}>
        <defs>
          <linearGradient id="spendFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={ARCANE} stopOpacity={0.5} />
            <stop offset="100%" stopColor={ARCANE} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={RUNE_LINE} strokeOpacity={0.4} vertical={false} />
        <XAxis
          dataKey="date"
          stroke={GHOST_DIM}
          tick={{ fill: GHOST_DIM, fontSize: 11 }}
          tickFormatter={(d: string) => d.slice(5)}
        />
        <YAxis
          stroke={GHOST_DIM}
          tick={{ fill: GHOST_DIM, fontSize: 11 }}
          tickFormatter={(v: number) => `$${v.toFixed(0)}`}
        />
        <Tooltip
          contentStyle={{
            background: "#0a0f1f",
            border: `1px solid ${RUNE_LINE}`,
            borderRadius: 6,
            color: GHOST,
          }}
          labelStyle={{ color: GHOST }}
          formatter={(v: unknown) => [`$${Number(v).toFixed(2)}`, "Spend"]}
        />
        <Area
          type="monotone"
          dataKey="cost_usd"
          stroke={ARCANE_BRIGHT}
          strokeWidth={2}
          fill="url(#spendFill)"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function ByProfile({ profiles }: { profiles: CostByProfile[] }) {
  if (profiles.length === 0) return <Empty label="No profile breakdown yet." />;
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={profiles} margin={{ top: 5, right: 8, bottom: 0, left: -16 }}>
        <CartesianGrid stroke={RUNE_LINE} strokeOpacity={0.4} vertical={false} />
        <XAxis dataKey="profile" stroke={GHOST_DIM} tick={{ fill: GHOST_DIM, fontSize: 11 }} />
        <YAxis
          stroke={GHOST_DIM}
          tick={{ fill: GHOST_DIM, fontSize: 11 }}
          tickFormatter={(v: number) => `$${v.toFixed(0)}`}
        />
        <Tooltip
          contentStyle={{
            background: "#0a0f1f",
            border: `1px solid ${RUNE_LINE}`,
            borderRadius: 6,
            color: GHOST,
          }}
          formatter={(v: unknown) => [`$${Number(v).toFixed(2)}`, "Spend"]}
        />
        <Bar dataKey="cost_usd" fill={ARCANE} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function TurnsHistogram({ buckets }: { buckets: TurnsBucket[] }) {
  const anyData = buckets.some((b) => b.count > 0);
  if (!anyData) return <Empty label="No turns recorded yet." />;
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={buckets} margin={{ top: 5, right: 8, bottom: 0, left: -16 }}>
        <CartesianGrid stroke={RUNE_LINE} strokeOpacity={0.4} vertical={false} />
        <XAxis dataKey="bucket" stroke={GHOST_DIM} tick={{ fill: GHOST_DIM, fontSize: 11 }} />
        <YAxis stroke={GHOST_DIM} tick={{ fill: GHOST_DIM, fontSize: 11 }} allowDecimals={false} />
        <Tooltip
          contentStyle={{
            background: "#0a0f1f",
            border: `1px solid ${RUNE_LINE}`,
            borderRadius: 6,
            color: GHOST,
          }}
        />
        <Bar dataKey="count" fill={ARCANE_BRIGHT} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function CostTable({ tickets }: { tickets: CostByTicket[] }) {
  if (tickets.length === 0) return <Empty label="No tickets yet." />;
  return (
    <div className="overflow-hidden rounded-md border border-rune-line">
      <table className="w-full text-sm">
        <thead className="bg-vault text-left text-xs uppercase tracking-wider text-ghost-dim">
          <tr>
            <th className="px-3 py-2">Ticket</th>
            <th className="px-3 py-2">State</th>
            <th className="px-3 py-2 text-right">Runs</th>
            <th className="px-3 py-2 text-right">Turns</th>
            <th className="px-3 py-2 text-right">Cost</th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((t) => (
            <tr key={t.ticket_key} className="border-t border-rune-line">
              <td className="px-3 py-2 font-medium text-ghost">{t.ticket_key}</td>
              <td className="px-3 py-2 text-ghost/80">{t.state}</td>
              <td className="px-3 py-2 text-right text-ghost/80">{t.runs}</td>
              <td className="px-3 py-2 text-right text-ghost/80">{t.turns}</td>
              <td className="px-3 py-2 text-right font-medium text-arcane">
                ${t.cost_usd.toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Empty({ label }: { label: string }) {
  return <p className="text-sm text-ghost-dimmer">{label}</p>;
}
