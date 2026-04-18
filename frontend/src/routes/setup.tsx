import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Loader2, Plus, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Dropdown } from "~/components/Dropdown";
import { Field, Segmented } from "~/components/Field";
import {
  type ConfigPayload,
  type LinearTeamSummary,
  useFetchLinearTeams,
  useSaveConfig,
  useTestConfig,
} from "~/lib/config";

export const Route = createFileRoute("/setup")({
  component: Setup,
});

interface RepoRow {
  name: string;
  path: string;
}

interface FormState {
  board_type: "linear" | "jira";
  linear: { api_key: string; team_id: string; watch_label: string };
  jira: { email: string; token: string; watch_label: string };
  agent_type: "claude_code" | "codex";
  claude_code: {
    auth_method: "personal_session" | "api_key";
    api_key: string;
    plugin_mode: "installed" | "local";
    plugin_path: string;
  };
  codex: { api_key: string };
  repos: RepoRow[];
  default_repo: string;
  polling_interval_sec: number;
  workspace_root: string;
}

const initialState: FormState = {
  board_type: "linear",
  linear: { api_key: "", team_id: "", watch_label: "task-summoner" },
  jira: { email: "", token: "", watch_label: "task-summoner" },
  agent_type: "claude_code",
  claude_code: {
    auth_method: "personal_session",
    api_key: "",
    plugin_mode: "installed",
    plugin_path: "",
  },
  codex: { api_key: "" },
  repos: [{ name: "", path: "" }],
  default_repo: "",
  polling_interval_sec: 10,
  workspace_root: "/tmp/task-summoner-workspaces",
};

function toPayload(s: FormState): ConfigPayload {
  const board_config = s.board_type === "linear" ? { ...s.linear } : { ...s.jira };
  const agent_config =
    s.agent_type === "claude_code"
      ? {
          auth_method: s.claude_code.auth_method,
          api_key: s.claude_code.auth_method === "api_key" ? s.claude_code.api_key : "",
          plugin_mode: s.claude_code.plugin_mode,
          plugin_path: s.claude_code.plugin_mode === "local" ? s.claude_code.plugin_path : "",
        }
      : { api_key: s.codex.api_key };
  const repos = Object.fromEntries(
    s.repos.filter((r) => r.name && r.path).map((r) => [r.name, r.path]),
  );
  return {
    board_type: s.board_type,
    board_config,
    agent_type: s.agent_type,
    agent_config,
    repos,
    default_repo: s.default_repo || (s.repos[0]?.name ?? ""),
    polling_interval_sec: s.polling_interval_sec,
    workspace_root: s.workspace_root,
  };
}

function Setup() {
  const navigate = useNavigate();
  const [form, setForm] = useState<FormState>(initialState);
  const save = useSaveConfig();
  const test = useTestConfig();

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await save.mutateAsync(toPayload(form));
    navigate({ to: "/monitor" });
  };

  const onTest = () => test.mutate(toPayload(form));

  const patchLinear = (k: keyof FormState["linear"], v: string) =>
    setForm((f) => ({ ...f, linear: { ...f.linear, [k]: v } }));
  const patchJira = (k: keyof FormState["jira"], v: string) =>
    setForm((f) => ({ ...f, jira: { ...f.jira, [k]: v } }));
  const patchClaude = (k: keyof FormState["claude_code"], v: string) =>
    setForm((f) => ({ ...f, claude_code: { ...f.claude_code, [k]: v } }));
  const patchCodex = (v: string) => setForm((f) => ({ ...f, codex: { api_key: v } }));

  const addRepo = () => setForm((f) => ({ ...f, repos: [...f.repos, { name: "", path: "" }] }));
  const removeRepo = (idx: number) =>
    setForm((f) => ({ ...f, repos: f.repos.filter((_, i) => i !== idx) }));
  const patchRepo = (idx: number, k: keyof RepoRow, v: string) =>
    setForm((f) => ({
      ...f,
      repos: f.repos.map((r, i) => (i === idx ? { ...r, [k]: v } : r)),
    }));

  return (
    <form onSubmit={onSubmit} className="max-w-3xl space-y-10">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold text-ghost-white">Setup</h1>
        <p className="text-soul-cyan/80">
          Wire up a board, an agent, and at least one repo. Test before saving if you want.
        </p>
      </header>

      <Section title="Board">
        <Segmented
          label="Provider"
          value={form.board_type}
          options={[
            { value: "linear", label: "Linear" },
            { value: "jira", label: "Jira" },
          ]}
          onChange={(v) => setForm((f) => ({ ...f, board_type: v }))}
        />
        {form.board_type === "linear" ? (
          <LinearBoardFields
            apiKey={form.linear.api_key}
            teamId={form.linear.team_id}
            watchLabel={form.linear.watch_label}
            onApiKeyChange={(v) => patchLinear("api_key", v)}
            onTeamIdChange={(v) => patchLinear("team_id", v)}
            onWatchLabelChange={(v) => patchLinear("watch_label", v)}
          />
        ) : (
          <>
            <Field
              label="Email"
              type="email"
              value={form.jira.email}
              onChange={(e) => patchJira("email", e.target.value)}
            />
            <Field
              label="API token"
              type="password"
              value={form.jira.token}
              onChange={(e) => patchJira("token", e.target.value)}
            />
            <Field
              label="Watch label"
              value={form.jira.watch_label}
              onChange={(e) => patchJira("watch_label", e.target.value)}
            />
          </>
        )}
      </Section>

      <Section title="Agent">
        <Segmented
          label="Provider"
          value={form.agent_type}
          options={[
            { value: "claude_code", label: "Claude Code" },
            { value: "codex", label: "Codex" },
          ]}
          onChange={(v) => setForm((f) => ({ ...f, agent_type: v }))}
        />
        {form.agent_type === "claude_code" ? (
          <>
            <Segmented
              label="Auth method"
              value={form.claude_code.auth_method}
              options={[
                { value: "personal_session", label: "Claude Code session" },
                { value: "api_key", label: "API key" },
              ]}
              onChange={(v) => patchClaude("auth_method", v)}
            />
            {form.claude_code.auth_method === "api_key" ? (
              <Field
                label="Anthropic API key"
                type="password"
                value={form.claude_code.api_key}
                onChange={(e) => patchClaude("api_key", e.target.value)}
                placeholder="sk-ant-..."
              />
            ) : null}
            <Segmented
              label="Plugin mode"
              value={form.claude_code.plugin_mode}
              options={[
                { value: "installed", label: "Installed" },
                { value: "local", label: "Local path" },
              ]}
              onChange={(v) => patchClaude("plugin_mode", v)}
            />
            {form.claude_code.plugin_mode === "local" ? (
              <Field
                label="Plugin path"
                value={form.claude_code.plugin_path}
                onChange={(e) => patchClaude("plugin_path", e.target.value)}
                placeholder="~/code/task-summoner-plugin/plugins/tmw-workflows"
              />
            ) : null}
          </>
        ) : (
          <Field
            label="API key"
            type="password"
            value={form.codex.api_key}
            onChange={(e) => patchCodex(e.target.value)}
          />
        )}
      </Section>

      <Section title="Repos">
        <div className="space-y-3">
          {form.repos.map((r, i) => (
            <div
              key={`repo-${
                // biome-ignore lint/suspicious/noArrayIndexKey: rows are identified by position
                i
              }`}
              className="flex items-end gap-3"
            >
              <div className="flex-1">
                <Field
                  label="Name"
                  value={r.name}
                  onChange={(e) => patchRepo(i, "name", e.target.value)}
                  placeholder="my-project"
                />
              </div>
              <div className="flex-[2]">
                <Field
                  label="Path"
                  value={r.path}
                  onChange={(e) => patchRepo(i, "path", e.target.value)}
                  placeholder="~/code/my-project"
                />
              </div>
              <button
                type="button"
                onClick={() => removeRepo(i)}
                disabled={form.repos.length === 1}
                className="mb-1 inline-flex h-10 w-10 items-center justify-center rounded-md border border-shadow-purple/60 text-soul-cyan/80 transition hover:border-ember-red/60 hover:text-ember-red disabled:cursor-not-allowed disabled:opacity-40"
                aria-label="Remove repo"
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={addRepo}
            className="inline-flex items-center gap-2 rounded-md border border-shadow-purple/60 bg-void-800/60 px-3 py-1.5 text-xs font-medium text-soul-cyan hover:border-arise-violet/70 hover:text-ghost-white"
          >
            <Plus size={14} /> Add repo
          </button>
        </div>
      </Section>

      <Section title="General">
        <Field
          label="Default repo"
          value={form.default_repo}
          onChange={(e) => setForm((f) => ({ ...f, default_repo: e.target.value }))}
          placeholder="my-project"
          hint="Used when a ticket has no repo:<name> label."
        />
        <Field
          label="Polling interval (seconds)"
          type="number"
          min={1}
          value={form.polling_interval_sec}
          onChange={(e) =>
            setForm((f) => ({
              ...f,
              polling_interval_sec: Number.parseInt(e.target.value, 10) || 10,
            }))
          }
        />
        <Field
          label="Workspace root"
          value={form.workspace_root}
          onChange={(e) => setForm((f) => ({ ...f, workspace_root: e.target.value }))}
        />
      </Section>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={save.isPending}
          className="glow-violet rounded-md border border-arise-violet/60 bg-arise-violet/20 px-5 py-2 text-sm font-medium text-ghost-white transition hover:bg-arise-violet/30 disabled:opacity-50"
        >
          {save.isPending ? "Saving..." : "Save config"}
        </button>
        <button
          type="button"
          onClick={onTest}
          disabled={test.isPending}
          className="rounded-md border border-shadow-purple/60 bg-void-800/60 px-5 py-2 text-sm font-medium text-soul-cyan transition hover:border-arise-violet/70 hover:text-ghost-white disabled:opacity-50"
        >
          {test.isPending ? "Testing..." : "Test"}
        </button>
        {test.data ? (
          <span
            className={["text-sm", test.data.ok ? "text-mana-green" : "text-ember-red"].join(" ")}
          >
            {test.data.message}
          </span>
        ) : null}
        {save.isError ? (
          <span className="text-sm text-ember-red">
            {save.error instanceof Error ? save.error.message : "Save failed"}
          </span>
        ) : null}
      </div>
    </form>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-4 rounded-lg border border-shadow-purple/60 bg-void-800/60 p-6">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-arise-violet-bright">
        {title}
      </h2>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

const TEAM_FETCH_DEBOUNCE_MS = 500;

function LinearBoardFields({
  apiKey,
  teamId,
  watchLabel,
  onApiKeyChange,
  onTeamIdChange,
  onWatchLabelChange,
}: {
  apiKey: string;
  teamId: string;
  watchLabel: string;
  onApiKeyChange: (v: string) => void;
  onTeamIdChange: (v: string) => void;
  onWatchLabelChange: (v: string) => void;
}) {
  const fetchTeams = useFetchLinearTeams();
  const [teams, setTeams] = useState<LinearTeamSummary[]>([]);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  // Auto-fetch teams after the API key settles (debounced). Latest key wins —
  // stale responses get dropped via the request-id guard. Only the apiKey
  // change should retrigger — teamId / callbacks are intentionally stale.
  // biome-ignore lint/correctness/useExhaustiveDependencies: see above
  useEffect(() => {
    const trimmed = apiKey.trim();
    if (!trimmed) {
      setTeams([]);
      setLookupError(null);
      return;
    }
    const myRequest = ++requestIdRef.current;
    const timer = window.setTimeout(() => {
      fetchTeams.mutate(trimmed, {
        onSuccess: (res) => {
          if (myRequest !== requestIdRef.current) return;
          if (!res.ok) {
            setTeams([]);
            setLookupError(res.message || "Lookup failed.");
            return;
          }
          setTeams(res.teams);
          setLookupError(null);
          const known = new Set(res.teams.map((t) => t.id));
          if (res.teams.length > 0 && !known.has(teamId)) {
            onTeamIdChange(res.teams[0]?.id ?? "");
          }
        },
        onError: (err) => {
          if (myRequest !== requestIdRef.current) return;
          setTeams([]);
          setLookupError(err instanceof Error ? err.message : "Lookup failed.");
        },
      });
    }, TEAM_FETCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [apiKey]);

  const options = teams.map((t) => ({
    value: t.id,
    label: `${t.name} (${t.key})`,
    hint: t.id,
  }));

  const showDropdown = teams.length > 0;

  return (
    <>
      <Field
        label="API key"
        type="password"
        value={apiKey}
        onChange={(e) => onApiKeyChange(e.target.value)}
        placeholder="lin_api_..."
        hint="Teams load automatically as you type."
      />

      {showDropdown ? (
        <div className="space-y-1">
          <Dropdown
            label="Team"
            value={teamId}
            onChange={onTeamIdChange}
            options={options}
            placeholder="Select a team"
          />
          <span className="block text-xs text-soul-cyan/70">
            Resolved {teams.length} team{teams.length === 1 ? "" : "s"}
            {teamId ? (
              <>
                {" — stored as "}
                <code className="font-mono text-[11px] text-ghost-white/90">{teamId}</code>.
              </>
            ) : (
              "."
            )}
          </span>
        </div>
      ) : (
        <Field
          label="Team ID"
          value={teamId}
          onChange={(e) => onTeamIdChange(e.target.value)}
          placeholder="fb14c704-25eb-..."
          hint={
            fetchTeams.isPending
              ? "Fetching teams…"
              : lookupError
                ? "Paste a UUID below, or fix the API key to retry."
                : "Paste a UUID, or fill the API key above to auto-load teams."
          }
        />
      )}

      {fetchTeams.isPending ? (
        <p className="flex items-center gap-1.5 text-xs text-soul-cyan/70">
          <Loader2 size={11} strokeWidth={2} className="animate-spin" />
          Fetching Linear teams…
        </p>
      ) : lookupError ? (
        <p className="text-xs text-ember-red">{lookupError}</p>
      ) : null}

      <Field
        label="Watch label"
        value={watchLabel}
        onChange={(e) => onWatchLabelChange(e.target.value)}
        hint="Tickets with this label are picked up by the orchestrator."
      />
    </>
  );
}
