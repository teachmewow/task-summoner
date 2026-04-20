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

// Hex palette for Recharts SVG (tailwind classes don't apply inside
// chart primitives). Keep in sync with the arcane theme in styles.css.
const ARCANE = "#36e0d0";
const ARCANE_BRIGHT = "#7beee4";
const BLOOD = "#ff5577";
const EMBER_TONE = "#ff8a5b";
const RUNE_LINE = "#2b3570";
const GHOST = "#eef2ff";
const GHOST_DIM = "#bcc5e6";

function Failures() {
  const { data, isLoading, isError } = useFailureSummary();
  const retry = useRetryTicket();

  if (isLoading) return <p className="text-ghost/80">Loading failures…</p>;
  if (isError || !data) return <p className="text-blood">Failed to load failures.</p>;

  return (
    <section className="space-y-8">
      <header className="space-y-1">
        <h1 className="text-3xl font-semibold text-ghost">Failure Analysis</h1>
        <p className="text-ghost/80">
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
    { label: "Total failed", value: total, tint: total > 0 ? BLOOD : GHOST },
    { label: "Quarantined", value: quarantined, tint: quarantined > 0 ? EMBER_TONE : GHOST },
    { label: "Healthy", value: healthy, tint: GHOST },
  ];
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {items.map((it) => (
        <div key={it.label} className="rounded-lg border border-rune-line-strong bg-vault-soft p-5">
          <p className="text-xs uppercase tracking-wider text-ghost-dim">{it.label}</p>
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
    <section className="rounded-lg border border-rune-line-strong bg-vault-soft p-5">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-arcane">{title}</h2>
      {children}
    </section>
  );
}

function ByPhase({ phases }: { phases: FailureByPhase[] }) {
  if (phases.length === 0) return <Empty label="No failures yet." />;
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={phases} margin={{ top: 5, right: 8, bottom: 0, left: -16 }}>
        <CartesianGrid stroke={RUNE_LINE} strokeOpacity={0.4} vertical={false} />
        <XAxis dataKey="phase" stroke={GHOST_DIM} tick={{ fill: GHOST_DIM, fontSize: 11 }} />
        <YAxis stroke={GHOST_DIM} tick={{ fill: GHOST_DIM, fontSize: 11 }} allowDecimals={false} />
        <Tooltip
          contentStyle={{
            background: "#0a0f1f",
            border: `1px solid ${RUNE_LINE}`,
            borderRadius: 6,
            color: GHOST,
          }}
        />
        <Bar dataKey="count" fill={BLOOD} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function ByCategory({ categories }: { categories: FailureByCategory[] }) {
  if (categories.length === 0) return <Empty label="No failures yet." />;
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={categories} margin={{ top: 5, right: 8, bottom: 0, left: -16 }}>
        <CartesianGrid stroke={RUNE_LINE} strokeOpacity={0.4} vertical={false} />
        <XAxis dataKey="category" stroke={GHOST_DIM} tick={{ fill: GHOST_DIM, fontSize: 11 }} />
        <YAxis stroke={GHOST_DIM} tick={{ fill: GHOST_DIM, fontSize: 11 }} allowDecimals={false} />
        <Tooltip
          contentStyle={{
            background: "#0a0f1f",
            border: `1px solid ${RUNE_LINE}`,
            borderRadius: 6,
            color: GHOST,
          }}
          formatter={(v: unknown, _name: unknown, ctx: { payload?: FailureByCategory }) => [
            `${Number(v)} · ${ctx.payload?.sample_message ?? ""}`,
            "Count",
          ]}
        />
        <Bar dataKey="count" fill={ARCANE} radius={[4, 4, 0, 0]} />
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
    <ul className="divide-y divide-rune-line">
      {tickets.map((t) => (
        <li key={t.ticket_key} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-start">
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-ghost">{t.ticket_key}</span>
              <CategoryPill category={t.category} />
              <PhasePill phase={t.last_phase} />
              {t.quarantined ? (
                <span className="rounded-full border border-ember/50 bg-ember/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-ember">
                  Quarantined
                </span>
              ) : null}
            </div>
            <p className="break-words text-sm text-ghost/80">{t.error || "—"}</p>
            <p className="text-xs text-ghost-dimmer">
              retries: {t.retry_count} · spent: ${t.total_cost_usd.toFixed(2)} · updated{" "}
              {t.updated_at.slice(0, 19).replace("T", " ")}
            </p>
          </div>
          <button
            type="button"
            onClick={() => onRetry(t.ticket_key)}
            disabled={retrying === t.ticket_key}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-rune-line-strong bg-vault px-3 py-1.5 text-xs font-medium text-ghost-dim transition hover:border-arcane/60 hover:text-ghost disabled:opacity-50"
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
    category === "board_not_found" ? EMBER_TONE : category === "timeout" ? BLOOD : ARCANE_BRIGHT;
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
    <span className="rounded-full border border-rune-line bg-vault px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-ghost/80">
      {phase}
    </span>
  );
}

function Empty({ label }: { label: string }) {
  return <p className="text-sm text-ghost-dimmer">{label}</p>;
}
