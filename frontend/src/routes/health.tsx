import { createFileRoute } from "@tanstack/react-router";
import { Activity, Box, CheckCircle2, HardDrive, Trash2, XCircle, Zap } from "lucide-react";
import type { ReactNode } from "react";
import {
  type AgentHealth,
  type BoardHealth,
  type LocalStateHealth,
  useClean,
  useHealth,
  useTestBoard,
} from "~/lib/health";

export const Route = createFileRoute("/health")({
  component: Health,
});

function Health() {
  const { data, isLoading, isError } = useHealth();
  const test = useTestBoard();
  const clean = useClean();

  if (isLoading) return <p className="text-ghost/80">Loading health…</p>;
  if (isError || !data) {
    return (
      <section className="space-y-2">
        <h1 className="text-2xl font-semibold text-ghost">Board Health</h1>
        <p className="text-blood">Couldn't load health. Configure Task Summoner first.</p>
      </section>
    );
  }

  return (
    <section className="space-y-8">
      <header className="space-y-1">
        <h1 className="text-3xl font-semibold text-ghost">Board Health</h1>
        <p className="text-ghost/80">
          Connection, agent, and local-state snapshot — polls every 10s.
        </p>
      </header>

      <div className="grid gap-4 lg:grid-cols-3">
        <BoardPanel
          board={data.board}
          onTest={() => test.mutate()}
          testing={test.isPending}
          testResult={
            test.data
              ? { ok: test.data.ok, message: test.data.message }
              : test.isError
                ? {
                    ok: false,
                    message: test.error instanceof Error ? test.error.message : "Test failed",
                  }
                : null
          }
        />
        <AgentPanel agent={data.agent} />
        <LocalPanel
          local={data.local}
          onClean={() => clean.mutate()}
          cleaning={clean.isPending}
          cleanResult={
            clean.data
              ? {
                  ok: clean.data.ok,
                  message:
                    clean.data.message +
                    (clean.data.removed.length
                      ? ` (${clean.data.removed.slice(0, 3).join(", ")}${
                          clean.data.removed.length > 3 ? "…" : ""
                        })`
                      : ""),
                }
              : clean.isError
                ? {
                    ok: false,
                    message: clean.error instanceof Error ? clean.error.message : "Clean failed",
                  }
                : null
          }
        />
      </div>
    </section>
  );
}

function Panel({
  icon,
  title,
  children,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-4 rounded-lg border border-rune-line-strong bg-vault-soft p-5">
      <div className="flex items-center gap-2">
        <span className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-rune-line-strong bg-vault text-arcane">
          {icon}
        </span>
        <h2 className="text-sm font-semibold uppercase tracking-wider text-arcane">{title}</h2>
      </div>
      {children}
    </section>
  );
}

function Row({ label, value, mono }: { label: string; value: ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-sm">
      <span className="text-ghost-dim">{label}</span>
      <span
        className={["min-w-0 truncate text-right text-ghost", mono ? "font-mono text-xs" : ""].join(
          " ",
        )}
      >
        {value}
      </span>
    </div>
  );
}

function Status({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={[
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wider",
        ok
          ? "border-phase-done/50 bg-phase-done/10 text-phase-done"
          : "border-blood/50 bg-blood/10 text-blood",
      ].join(" ")}
    >
      {ok ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
      {label}
    </span>
  );
}

function BoardPanel({
  board,
  onTest,
  testing,
  testResult,
}: {
  board: BoardHealth;
  onTest: () => void;
  testing: boolean;
  testResult: { ok: boolean; message: string } | null;
}) {
  return (
    <Panel icon={<Activity size={16} strokeWidth={1.75} />} title="Board provider">
      <div className="flex items-center justify-between">
        <Status ok={board.configured} label={board.configured ? "Configured" : "Missing"} />
        <span className="text-xs uppercase tracking-wider text-ghost-dim">{board.provider}</span>
      </div>
      <div className="space-y-1.5">
        <Row label="Watch label" value={board.watch_label || "—"} mono />
        <Row label="Identifier" value={board.identifier || "—"} mono />
        <Row
          label="Last OK"
          value={board.last_ok_at ? board.last_ok_at.slice(0, 19).replace("T", " ") : "never"}
          mono
        />
        {board.last_error ? (
          <Row label="Last error" value={<span className="text-blood">{board.last_error}</span>} />
        ) : null}
      </div>
      <button
        type="button"
        onClick={onTest}
        disabled={testing}
        className="inline-flex items-center justify-center gap-1.5 rounded-md border border-arcane/60 bg-arcane/20 px-3 py-1.5 text-xs font-medium text-ghost transition hover:bg-arcane/30 disabled:opacity-50"
      >
        <Zap size={12} strokeWidth={2} />
        {testing ? "Testing…" : "Test connection"}
      </button>
      {testResult ? (
        <p className={testResult.ok ? "text-xs text-phase-done" : "text-xs text-blood"}>
          {testResult.message}
        </p>
      ) : null}
    </Panel>
  );
}

function AgentPanel({ agent }: { agent: AgentHealth }) {
  const sessionLabel =
    agent.provider === "codex"
      ? "Not implemented"
      : agent.session_available
        ? "Session detected"
        : "No session";
  return (
    <Panel icon={<Box size={16} strokeWidth={1.75} />} title="Agent provider">
      <div className="flex items-center justify-between">
        <Status ok={agent.session_available} label={sessionLabel} />
        <span className="text-xs uppercase tracking-wider text-ghost-dim">{agent.provider}</span>
      </div>
      <div className="space-y-1.5">
        <Row label="Plugin mode" value={agent.plugin_mode || "—"} mono />
        <Row label="Plugin path" value={agent.plugin_path || "—"} mono />
        <Row
          label="Plugin resolved"
          value={
            agent.plugin_resolved ? (
              <span className="text-phase-done">yes</span>
            ) : (
              <span className="text-blood">no</span>
            )
          }
        />
        {agent.plugin_reason ? (
          <p className="pt-1 text-xs text-ember">{agent.plugin_reason}</p>
        ) : null}
      </div>
    </Panel>
  );
}

function LocalPanel({
  local,
  onClean,
  cleaning,
  cleanResult,
}: {
  local: LocalStateHealth;
  onClean: () => void;
  cleaning: boolean;
  cleanResult: { ok: boolean; message: string } | null;
}) {
  return (
    <Panel icon={<HardDrive size={16} strokeWidth={1.75} />} title="Local state">
      <div className="grid grid-cols-3 gap-2">
        <Mini label="Total" value={String(local.total_tickets)} />
        <Mini label="Active" value={String(local.active_tickets)} />
        <Mini label="Terminal" value={String(local.terminal_tickets)} />
      </div>
      <div className="space-y-1.5">
        <Row label="Workspace" value={`${formatBytes(local.workspace_bytes)}`} mono />
        <Row label="Workspace path" value={local.workspace_root} mono />
        <Row label="Artifacts" value={formatBytes(local.artifacts_bytes)} mono />
        <Row label="Artifacts path" value={local.artifacts_dir} mono />
      </div>
      <button
        type="button"
        onClick={onClean}
        disabled={cleaning}
        className="inline-flex items-center justify-center gap-1.5 rounded-md border border-blood/50 bg-blood/10 px-3 py-1.5 text-xs font-medium text-blood transition hover:bg-blood/20 disabled:opacity-50"
      >
        <Trash2 size={12} strokeWidth={2} />
        {cleaning ? "Cleaning…" : "Run clean"}
      </button>
      {cleanResult ? (
        <p className={cleanResult.ok ? "text-xs text-phase-done" : "text-xs text-blood"}>
          {cleanResult.message}
        </p>
      ) : null}
    </Panel>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-rune-line bg-vault/70 p-2 text-center">
      <p className="text-[10px] uppercase tracking-wider text-ghost-dim">{label}</p>
      <p className="text-lg font-semibold text-ghost">{value}</p>
    </div>
  );
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}
