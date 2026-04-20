import { createFileRoute } from "@tanstack/react-router";
import { Save } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { Field } from "~/components/Field";
import {
  type AgentProfile,
  type AgentProfilePayload,
  useAgentProfiles,
  useSaveAgentProfile,
} from "~/lib/agents";

export const Route = createFileRoute("/agents")({
  component: Agents,
});

const ALL_TOOLS = ["Read", "Glob", "Grep", "Bash", "Edit", "Write", "Skill"] as const;

function Agents() {
  const { data, isLoading, isError } = useAgentProfiles();

  if (isLoading) return <p className="text-ghost/80">Loading profiles…</p>;
  if (isError || !data) {
    return (
      <section className="space-y-2">
        <h1 className="text-2xl font-semibold text-ghost">Agent Configurator</h1>
        <p className="text-blood">
          Couldn't load agent profiles. If you haven't configured Task Summoner yet, run setup
          first.
        </p>
      </section>
    );
  }

  return (
    <section className="space-y-8">
      <header className="space-y-1">
        <h1 className="text-3xl font-semibold text-ghost">Agent Configurator</h1>
        <p className="text-ghost/80">
          Provider: <span className="text-ghost">{data.agent_provider}</span> · models supported:{" "}
          {data.available_models.join(", ") || "n/a"}
        </p>
      </header>

      <div className="grid gap-4 lg:grid-cols-3">
        {data.profiles.map((p) => (
          <ProfileCard key={p.name} profile={p} availableModels={data.available_models} />
        ))}
      </div>
    </section>
  );
}

function ProfileCard({
  profile,
  availableModels,
}: {
  profile: AgentProfile;
  availableModels: string[];
}) {
  const [form, setForm] = useState<AgentProfilePayload>({
    model: profile.model,
    max_turns: profile.max_turns,
    max_budget_usd: profile.max_budget_usd,
    tools: profile.tools,
    enabled: profile.enabled,
  });
  const save = useSaveAgentProfile();

  useEffect(() => {
    setForm({
      model: profile.model,
      max_turns: profile.max_turns,
      max_budget_usd: profile.max_budget_usd,
      tools: profile.tools,
      enabled: profile.enabled,
    });
  }, [profile.model, profile.max_turns, profile.max_budget_usd, profile.enabled, profile.tools]);

  const toggleTool = (tool: string) =>
    setForm((f) => ({
      ...f,
      tools: f.tools.includes(tool) ? f.tools.filter((t) => t !== tool) : [...f.tools, tool],
    }));

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    save.mutate({ name: profile.name, payload: form });
  };

  const dirty =
    form.model !== profile.model ||
    form.max_turns !== profile.max_turns ||
    form.max_budget_usd !== profile.max_budget_usd ||
    form.enabled !== profile.enabled ||
    JSON.stringify([...form.tools].sort()) !== JSON.stringify([...profile.tools].sort());

  return (
    <form
      onSubmit={onSubmit}
      className="flex flex-col gap-4 rounded-lg border border-rune-line-strong bg-vault-soft p-5"
    >
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-arcane">
          {profile.name.replace("_", " ")}
        </h2>
        <label className="inline-flex items-center gap-2 text-xs text-ghost/80">
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
            className="accent-arcane"
          />
          Enabled
        </label>
      </div>

      <Row label="Model">
        <select
          value={form.model}
          onChange={(e) => setForm((f) => ({ ...f, model: e.target.value }))}
          className="w-full rounded-md border border-rune-line-strong bg-vault px-3 py-2 text-sm text-ghost focus:border-arcane focus:outline-none focus:ring-2 focus:ring-arcane/40"
        >
          {availableModels.length === 0 ? <option value={form.model}>{form.model}</option> : null}
          {availableModels.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </Row>

      <Field
        label="Max turns"
        type="number"
        min={1}
        value={form.max_turns}
        onChange={(e) =>
          setForm((f) => ({ ...f, max_turns: Number.parseInt(e.target.value, 10) || 0 }))
        }
      />

      <Field
        label="Max budget (USD)"
        type="number"
        min={0}
        step="0.1"
        value={form.max_budget_usd}
        onChange={(e) =>
          setForm((f) => ({ ...f, max_budget_usd: Number.parseFloat(e.target.value) || 0 }))
        }
      />

      <Row label="Tools">
        <div className="flex flex-wrap gap-2">
          {ALL_TOOLS.map((tool) => {
            const on = form.tools.includes(tool);
            return (
              <button
                key={tool}
                type="button"
                onClick={() => toggleTool(tool)}
                className={[
                  "rounded-full border px-3 py-1 text-xs font-medium transition",
                  on
                    ? "border-arcane/60 bg-arcane/20 text-ghost"
                    : "border-rune-line bg-vault text-ghost/80 hover:border-arcane/40 hover:text-ghost",
                ].join(" ")}
              >
                {tool}
              </button>
            );
          })}
        </div>
      </Row>

      <div className="flex items-center gap-3 pt-1">
        <button
          type="submit"
          disabled={!dirty || save.isPending}
          className="inline-flex items-center gap-1.5 rounded-md border border-arcane/60 bg-arcane/20 px-3 py-1.5 text-xs font-medium text-ghost transition hover:bg-arcane/30 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Save size={12} strokeWidth={2} />
          {save.isPending && save.variables?.name === profile.name ? "Saving…" : "Save"}
        </button>
        {save.isSuccess && save.data?.profile.name === profile.name && !dirty ? (
          <span className="text-xs text-phase-done">Saved ✓</span>
        ) : null}
        {save.isError && save.variables?.name === profile.name ? (
          <span className="text-xs text-blood">
            {save.error instanceof Error ? save.error.message : "Save failed"}
          </span>
        ) : null}
      </div>
    </form>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <span className="text-sm font-medium text-ghost">{label}</span>
      {children}
    </div>
  );
}
