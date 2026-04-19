import { createFileRoute } from "@tanstack/react-router";
import { CheckCircle2, Loader2, Plus, Trash2, XCircle } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Dropdown } from "~/components/Dropdown";
import { Segmented } from "~/components/Field";
import {
  type LinearTeamSummary,
  MASKED_SECRET_SENTINEL,
  type SetupSavePayload,
  type SetupStateResponse,
  useFetchLinearTeams,
  useSaveSetup,
  useSetupState,
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
  docs_repo: string;
}

const emptyState: FormState = {
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
  docs_repo: "",
};

function stateFromResponse(res: SetupStateResponse): FormState {
  const next: FormState = { ...emptyState };
  if (res.board.provider === "linear") {
    next.board_type = "linear";
    next.linear = {
      api_key: res.board.api_key ?? "",
      team_id: res.board.team_id ?? "",
      watch_label: res.board.watch_label || "task-summoner",
    };
  } else if (res.board.provider === "jira") {
    next.board_type = "jira";
    next.jira = {
      email: res.board.email ?? "",
      token: res.board.api_key ?? "",
      watch_label: res.board.watch_label || "task-summoner",
    };
  }

  if (res.agent.provider === "claude_code") {
    next.agent_type = "claude_code";
    next.claude_code = {
      auth_method: res.agent.auth_method === "api_key" ? "api_key" : "personal_session",
      api_key: res.agent.api_key ?? "",
      plugin_mode: res.agent.plugin_mode === "local" ? "local" : "installed",
      plugin_path: res.agent.plugin_path ?? "",
    };
  } else if (res.agent.provider === "codex") {
    next.agent_type = "codex";
    next.codex = { api_key: res.agent.api_key ?? "" };
  }

  next.repos = res.repos.length > 0 ? res.repos.map((r) => ({ ...r })) : [{ name: "", path: "" }];
  next.default_repo = res.general.default_repo ?? "";
  next.polling_interval_sec = res.general.polling_interval_sec || 10;
  next.workspace_root = res.general.workspace_root || "/tmp/task-summoner-workspaces";
  next.docs_repo = res.general.docs_repo ?? "";
  return next;
}

function toSavePayload(s: FormState): SetupSavePayload {
  const board =
    s.board_type === "linear"
      ? {
          provider: "linear",
          api_key: s.linear.api_key,
          team_id: s.linear.team_id,
          watch_label: s.linear.watch_label,
        }
      : {
          provider: "jira",
          email: s.jira.email,
          api_key: s.jira.token,
          watch_label: s.jira.watch_label,
        };
  const agent =
    s.agent_type === "claude_code"
      ? {
          provider: "claude_code",
          auth_method: s.claude_code.auth_method,
          api_key: s.claude_code.auth_method === "api_key" ? s.claude_code.api_key : "",
          plugin_mode: s.claude_code.plugin_mode,
          plugin_path: s.claude_code.plugin_mode === "local" ? s.claude_code.plugin_path : "",
        }
      : { provider: "codex", api_key: s.codex.api_key };
  const repos = s.repos.filter((r) => r.name && r.path).map((r) => ({ ...r }));
  return {
    board,
    agent,
    repos,
    general: {
      default_repo: s.default_repo || (s.repos[0]?.name ?? ""),
      polling_interval_sec: s.polling_interval_sec,
      workspace_root: s.workspace_root,
      docs_repo: s.docs_repo,
    },
  };
}

// Compare two nested states deeply enough to mark modified fields. Returns
// a flat map of dot.paths to boolean. Only paths rendered in the form are
// consulted; extra entries are harmless.
type DirtyMap = Record<string, boolean>;

function computeDirty(current: FormState, baseline: FormState): DirtyMap {
  const dirty: DirtyMap = {};
  const add = (path: string, a: unknown, b: unknown) => {
    dirty[path] = a !== b;
  };
  add("board_type", current.board_type, baseline.board_type);
  add("linear.api_key", current.linear.api_key, baseline.linear.api_key);
  add("linear.team_id", current.linear.team_id, baseline.linear.team_id);
  add("linear.watch_label", current.linear.watch_label, baseline.linear.watch_label);
  add("jira.email", current.jira.email, baseline.jira.email);
  add("jira.token", current.jira.token, baseline.jira.token);
  add("jira.watch_label", current.jira.watch_label, baseline.jira.watch_label);
  add("agent_type", current.agent_type, baseline.agent_type);
  add("claude_code.auth_method", current.claude_code.auth_method, baseline.claude_code.auth_method);
  add("claude_code.api_key", current.claude_code.api_key, baseline.claude_code.api_key);
  add("claude_code.plugin_mode", current.claude_code.plugin_mode, baseline.claude_code.plugin_mode);
  add("claude_code.plugin_path", current.claude_code.plugin_path, baseline.claude_code.plugin_path);
  add("codex.api_key", current.codex.api_key, baseline.codex.api_key);
  add("default_repo", current.default_repo, baseline.default_repo);
  add("polling_interval_sec", current.polling_interval_sec, baseline.polling_interval_sec);
  add("workspace_root", current.workspace_root, baseline.workspace_root);
  add("docs_repo", current.docs_repo, baseline.docs_repo);
  dirty.repos = JSON.stringify(current.repos) !== JSON.stringify(baseline.repos);
  return dirty;
}

function isAnyDirty(d: DirtyMap): boolean {
  return Object.values(d).some(Boolean);
}

function Setup() {
  const state = useSetupState();
  const save = useSaveSetup();
  const [form, setForm] = useState<FormState>(emptyState);
  const [baseline, setBaseline] = useState<FormState>(emptyState);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (state.data) {
      const next = stateFromResponse(state.data);
      setForm(next);
      setBaseline(next);
    }
  }, [state.data]);

  const dirty = useMemo(() => computeDirty(form, baseline), [form, baseline]);
  const dirtyAny = isAnyDirty(dirty);

  // Path validation that runs on blur. Each key holds the latest status so the
  // UI can show check/red icons next to the field.
  const [pathStatus, setPathStatus] = useState<Record<string, PathStatus>>({});
  const anyPathInvalid = Object.values(pathStatus).some((s) => s.ok === false);

  const onPathBlur = async (key: string, value: string) => {
    if (!value.trim()) {
      setPathStatus((p) => ({ ...p, [key]: { ok: null } }));
      return;
    }
    setPathStatus((p) => ({ ...p, [key]: { ok: null, checking: true } }));
    const ok = await quickPathCheck(value);
    setPathStatus((p) => ({ ...p, [key]: { ok, checking: false } }));
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!dirtyAny || anyPathInvalid) return;
    const res = await save.mutateAsync(toSavePayload(form));
    if (res.ok) {
      setToast("Saved. Orchestrator reloaded.");
      window.setTimeout(() => setToast(null), 3_000);
    }
  };

  const patch = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    setForm((f) => ({ ...f, [k]: v }));
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

  if (state.isLoading) {
    return <p className="text-sm text-soul-cyan/80">Loading saved config…</p>;
  }

  const saveBlocked = !dirtyAny || anyPathInvalid || save.isPending;
  const linearApiMasked = baseline.linear.api_key === MASKED_SECRET_SENTINEL;
  const jiraTokenMasked = baseline.jira.token === MASKED_SECRET_SENTINEL;
  const claudeKeyMasked = baseline.claude_code.api_key === MASKED_SECRET_SENTINEL;
  const codexKeyMasked = baseline.codex.api_key === MASKED_SECRET_SENTINEL;

  return (
    <form onSubmit={onSubmit} className="max-w-3xl space-y-10">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold text-ghost-white">Setup</h1>
        <p className="text-soul-cyan/80">
          Wire up a board, an agent, and at least one repo. Fields you haven't changed carry over
          from the last save.
        </p>
      </header>

      <Section title="Board" modified={dirty.board_type}>
        <Segmented
          label="Provider"
          value={form.board_type}
          options={[
            { value: "linear", label: "Linear" },
            { value: "jira", label: "Jira" },
          ]}
          onChange={(v) => patch("board_type", v)}
        />
        {form.board_type === "linear" ? (
          <LinearBoardFields
            apiKey={form.linear.api_key}
            apiKeyMasked={linearApiMasked}
            teamId={form.linear.team_id}
            watchLabel={form.linear.watch_label}
            onApiKeyChange={(v) => patchLinear("api_key", v)}
            onTeamIdChange={(v) => patchLinear("team_id", v)}
            onWatchLabelChange={(v) => patchLinear("watch_label", v)}
            dirtyApiKey={dirty["linear.api_key"]}
            dirtyTeamId={dirty["linear.team_id"]}
            dirtyLabel={dirty["linear.watch_label"]}
          />
        ) : (
          <>
            <FieldWithDot
              label="Email"
              type="email"
              value={form.jira.email}
              onChange={(e) => patchJira("email", e.target.value)}
              modified={dirty["jira.email"]}
            />
            <FieldWithDot
              label="API token"
              type={jiraTokenMasked && !dirty["jira.token"] ? "text" : "password"}
              value={form.jira.token}
              onChange={(e) => patchJira("token", e.target.value)}
              modified={dirty["jira.token"]}
              maskControls={{
                isMasked: jiraTokenMasked && !dirty["jira.token"],
                onReplace: () => patchJira("token", ""),
              }}
            />
            <FieldWithDot
              label="Watch label"
              value={form.jira.watch_label}
              onChange={(e) => patchJira("watch_label", e.target.value)}
              modified={dirty["jira.watch_label"]}
            />
          </>
        )}
      </Section>

      <Section title="Agent" modified={dirty.agent_type}>
        <Segmented
          label="Provider"
          value={form.agent_type}
          options={[
            { value: "claude_code", label: "Claude Code" },
            { value: "codex", label: "Codex" },
          ]}
          onChange={(v) => patch("agent_type", v)}
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
              <FieldWithDot
                label="Anthropic API key"
                type={claudeKeyMasked && !dirty["claude_code.api_key"] ? "text" : "password"}
                value={form.claude_code.api_key}
                onChange={(e) => patchClaude("api_key", e.target.value)}
                placeholder="sk-ant-..."
                modified={dirty["claude_code.api_key"]}
                maskControls={{
                  isMasked: claudeKeyMasked && !dirty["claude_code.api_key"],
                  onReplace: () => patchClaude("api_key", ""),
                }}
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
              <FieldWithDot
                label="Plugin path"
                value={form.claude_code.plugin_path}
                onChange={(e) => patchClaude("plugin_path", e.target.value)}
                onBlur={(e) => onPathBlur("plugin_path", e.target.value)}
                placeholder="~/code/task-summoner-plugin/plugins/task-summoner-workflows"
                modified={dirty["claude_code.plugin_path"]}
                pathStatus={pathStatus.plugin_path}
              />
            ) : null}
          </>
        ) : (
          <FieldWithDot
            label="API key"
            type={codexKeyMasked && !dirty["codex.api_key"] ? "text" : "password"}
            value={form.codex.api_key}
            onChange={(e) => patchCodex(e.target.value)}
            modified={dirty["codex.api_key"]}
            maskControls={{
              isMasked: codexKeyMasked && !dirty["codex.api_key"],
              onReplace: () => patchCodex(""),
            }}
          />
        )}
      </Section>

      <Section title="Repos" modified={dirty.repos}>
        <div className="space-y-3">
          {form.repos.map((r, i) => {
            const pathKey = `repo.${i}.path`;
            return (
              <div
                key={`repo-${
                  // biome-ignore lint/suspicious/noArrayIndexKey: rows identified by position
                  i
                }`}
                className="flex items-end gap-3"
              >
                <div className="flex-1">
                  <FieldWithDot
                    label="Name"
                    value={r.name}
                    onChange={(e) => patchRepo(i, "name", e.target.value)}
                    placeholder="my-project"
                    modified={false}
                  />
                </div>
                <div className="flex-[2]">
                  <FieldWithDot
                    label="Path"
                    value={r.path}
                    onChange={(e) => patchRepo(i, "path", e.target.value)}
                    onBlur={(e) => onPathBlur(pathKey, e.target.value)}
                    placeholder="~/code/my-project"
                    modified={false}
                    pathStatus={pathStatus[pathKey]}
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
            );
          })}
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
        <FieldWithDot
          label="Default repo"
          value={form.default_repo}
          onChange={(e) => patch("default_repo", e.target.value)}
          placeholder="my-project"
          hint="Used when a ticket has no repo:<name> label."
          modified={dirty.default_repo}
        />
        <FieldWithDot
          label="Polling interval (seconds)"
          type="number"
          min={1}
          value={form.polling_interval_sec}
          onChange={(e) => patch("polling_interval_sec", Number.parseInt(e.target.value, 10) || 10)}
          modified={dirty.polling_interval_sec}
        />
        <FieldWithDot
          label="Workspace root"
          value={form.workspace_root}
          onChange={(e) => patch("workspace_root", e.target.value)}
          modified={dirty.workspace_root}
        />
      </Section>

      <Section title="Advanced paths">
        <FieldWithDot
          label="Docs repo path"
          value={form.docs_repo}
          onChange={(e) => patch("docs_repo", e.target.value)}
          onBlur={(e) => onPathBlur("docs_repo", e.target.value)}
          placeholder="/Users/you/code/my-docs-repo"
          hint="Local clone of task-summoner-docs-template. Required for design-doc skills."
          modified={dirty.docs_repo}
          pathStatus={pathStatus.docs_repo}
        />
      </Section>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={saveBlocked}
          className="glow-violet rounded-md border border-arise-violet/60 bg-arise-violet/20 px-5 py-2 text-sm font-medium text-ghost-white transition hover:bg-arise-violet/30 disabled:opacity-50"
        >
          {save.isPending ? "Saving..." : "Save config"}
        </button>
        {toast ? <span className="text-sm text-mana-green">{toast}</span> : null}
        {save.isError ? (
          <span className="text-sm text-ember-red">
            {save.error instanceof Error ? save.error.message : "Save failed"}
          </span>
        ) : null}
        {save.data && !save.data.ok ? (
          <span className="text-sm text-ember-red">{save.data.errors.join("; ")}</span>
        ) : null}
      </div>
    </form>
  );
}

interface PathStatus {
  ok: boolean | null;
  checking?: boolean;
}

async function quickPathCheck(value: string): Promise<boolean> {
  // Frontend-only sanity: absolute path and non-empty. Deeper validation
  // (git repo + .task-summoner/config.yml) runs server-side on save; the
  // inline indicator here is best-effort UX.
  const trimmed = value.trim();
  if (!trimmed) return true;
  if (!trimmed.startsWith("/") && !trimmed.startsWith("~")) return false;
  return true;
}

function Section({
  title,
  modified,
  children,
}: {
  title: string;
  modified?: boolean | undefined;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-4 rounded-lg border border-shadow-purple/60 bg-void-800/60 p-6">
      <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-arise-violet-bright">
        {title}
        {modified ? (
          <span
            aria-label="modified"
            data-testid="section-modified-dot"
            className="inline-block h-1.5 w-1.5 rounded-full bg-arise-violet"
          />
        ) : null}
      </h2>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

interface FieldWithDotProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: string | undefined;
  modified?: boolean | undefined;
  pathStatus?: PathStatus | undefined;
  maskControls?:
    | {
        isMasked: boolean;
        onReplace: () => void;
      }
    | undefined;
}

function FieldWithDot({
  modified,
  pathStatus,
  maskControls,
  label,
  hint,
  id,
  ...rest
}: FieldWithDotProps) {
  const inputId = id ?? `field-${label.toLowerCase().replace(/\s+/g, "-")}`;
  const dotTestId = `field-modified-dot-${label.toLowerCase().replace(/\s+/g, "-")}`;
  return (
    <label htmlFor={inputId} className="block space-y-1">
      <span className="flex items-center gap-2 text-sm font-medium text-ghost-white">
        {label}
        {modified ? (
          <span
            aria-label="modified"
            data-testid={dotTestId}
            className="inline-block h-1.5 w-1.5 rounded-full bg-arise-violet"
          />
        ) : null}
        {pathStatus?.ok === true ? (
          <CheckCircle2 size={12} className="text-mana-green" />
        ) : pathStatus?.ok === false ? (
          <XCircle size={12} className="text-ember-red" />
        ) : null}
      </span>
      <input
        id={inputId}
        {...rest}
        className="w-full rounded-md border border-shadow-purple/60 bg-void-900/60 px-3 py-2 text-sm text-ghost-white placeholder:text-soul-cyan/40 focus:border-arise-violet focus:outline-none focus:ring-2 focus:ring-arise-violet/40"
      />
      {hint ? <span className="block text-xs text-soul-cyan/70">{hint}</span> : null}
      {maskControls?.isMasked ? (
        <button
          type="button"
          onClick={maskControls.onReplace}
          className="text-xs text-soul-cyan underline hover:text-ghost-white"
        >
          Replace
        </button>
      ) : null}
      {pathStatus?.ok === false ? (
        <p className="text-xs text-ember-red">Path looks off — must be absolute.</p>
      ) : null}
    </label>
  );
}

const TEAM_FETCH_DEBOUNCE_MS = 500;

function LinearBoardFields({
  apiKey,
  apiKeyMasked,
  teamId,
  watchLabel,
  onApiKeyChange,
  onTeamIdChange,
  onWatchLabelChange,
  dirtyApiKey,
  dirtyTeamId,
  dirtyLabel,
}: {
  apiKey: string;
  apiKeyMasked: boolean;
  teamId: string;
  watchLabel: string;
  onApiKeyChange: (v: string) => void;
  onTeamIdChange: (v: string) => void;
  onWatchLabelChange: (v: string) => void;
  dirtyApiKey?: boolean | undefined;
  dirtyTeamId?: boolean | undefined;
  dirtyLabel?: boolean | undefined;
}) {
  const fetchTeams = useFetchLinearTeams();
  const [teams, setTeams] = useState<LinearTeamSummary[]>([]);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  // Auto-fetch teams after the API key settles (debounced). Skip when the
  // field still holds the mask sentinel — no need to hit Linear with "*******".
  // biome-ignore lint/correctness/useExhaustiveDependencies: only apiKey should retrigger
  useEffect(() => {
    const trimmed = apiKey.trim();
    if (!trimmed || trimmed === MASKED_SECRET_SENTINEL) {
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
      <FieldWithDot
        label="API key"
        type={apiKeyMasked && !dirtyApiKey ? "text" : "password"}
        value={apiKey}
        onChange={(e) => onApiKeyChange(e.target.value)}
        placeholder="lin_api_..."
        hint="Teams load automatically as you type."
        modified={dirtyApiKey}
        maskControls={{
          isMasked: apiKeyMasked && !dirtyApiKey,
          onReplace: () => onApiKeyChange(""),
        }}
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
        <FieldWithDot
          label="Team ID"
          value={teamId}
          onChange={(e) => onTeamIdChange(e.target.value)}
          placeholder="fb14c704-25eb-..."
          modified={dirtyTeamId}
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

      <FieldWithDot
        label="Watch label"
        value={watchLabel}
        onChange={(e) => onWatchLabelChange(e.target.value)}
        hint="Tickets with this label are picked up by the orchestrator."
        modified={dirtyLabel}
      />
    </>
  );
}
