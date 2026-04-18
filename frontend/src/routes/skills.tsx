import { createFileRoute } from "@tanstack/react-router";
import { AlertTriangle, FileText, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { type SkillSummary, useSaveSkill, useSkill, useSkills } from "~/lib/skills";

export const Route = createFileRoute("/skills")({
  component: Skills,
});

function Skills() {
  const { data, isLoading, isError } = useSkills();
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    if (!selected && data?.skills.length) setSelected(data.skills[0]?.name ?? null);
  }, [data, selected]);

  if (isLoading) return <p className="text-soul-cyan/80">Loading skills…</p>;
  if (isError || !data) {
    return (
      <section className="space-y-2">
        <h1 className="text-2xl font-semibold text-ghost-white">Skills Editor</h1>
        <p className="text-ember-red">Couldn't load skills. Configure Task Summoner first.</p>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-3xl font-semibold text-ghost-white">Skills Editor</h1>
        <p className="text-soul-cyan/80">
          {data.plugin_mode === "local" ? "Local plugin" : "Installed plugin"} ·{" "}
          <code className="text-ghost-white/90">
            {data.resolved_from || data.plugin_path || "unresolved"}
          </code>
        </p>
        {data.reason ? <ReadOnlyNotice reason={data.reason} /> : null}
      </header>

      {data.skills.length === 0 ? (
        <p className="text-soul-cyan/70">No SKILL.md files found under the plugin path.</p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
          <SkillList skills={data.skills} selected={selected} onSelect={setSelected} />
          {selected ? (
            <Editor name={selected} editable={data.editable} />
          ) : (
            <div className="rounded-lg border border-shadow-purple/60 bg-void-800/70 p-6 text-sm text-soul-cyan/70">
              Pick a skill on the left to start editing.
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function ReadOnlyNotice({ reason }: { reason: string }) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-amber-flame/40 bg-amber-flame/10 px-3 py-2 text-sm text-amber-flame">
      <AlertTriangle size={14} strokeWidth={2} className="mt-0.5 shrink-0" />
      <span>{reason}</span>
    </div>
  );
}

function SkillList({
  skills,
  selected,
  onSelect,
}: {
  skills: SkillSummary[];
  selected: string | null;
  onSelect: (name: string) => void;
}) {
  return (
    <ul className="flex max-h-[600px] flex-col gap-1 overflow-y-auto rounded-lg border border-shadow-purple/60 bg-void-800/70 p-2">
      {skills.map((s) => (
        <li key={s.name}>
          <button
            type="button"
            onClick={() => onSelect(s.name)}
            className={[
              "flex w-full items-start gap-2 rounded-md px-3 py-2 text-left transition",
              selected === s.name
                ? "bg-arise-violet/20 text-ghost-white shadow-[0_0_0_1px_rgba(168,85,247,0.45)]"
                : "text-soul-cyan/85 hover:bg-void-700/60 hover:text-ghost-white",
            ].join(" ")}
          >
            <FileText size={14} strokeWidth={2} className="mt-1 shrink-0 text-arise-violet" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">{s.name}</span>
              <span className="block truncate text-xs text-soul-cyan/60">
                {s.description || "—"}
              </span>
            </span>
            {s.user_invocable ? (
              <span className="mt-0.5 rounded-full border border-arise-violet/40 bg-arise-violet/10 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wider text-arise-violet-bright">
                /user
              </span>
            ) : null}
          </button>
        </li>
      ))}
    </ul>
  );
}

function Editor({ name, editable }: { name: string; editable: boolean }) {
  const { data, isLoading, isError } = useSkill(name);
  const save = useSaveSkill();
  const [draft, setDraft] = useState<string>("");
  const [lastSavedAt, setLastSavedAt] = useState<string | null>(null);

  useEffect(() => {
    if (data) setDraft(data.content);
  }, [data]);

  if (isLoading) return <p className="text-soul-cyan/80">Loading skill…</p>;
  if (isError || !data) {
    return <p className="text-ember-red">Failed to load skill.</p>;
  }

  const dirty = draft !== data.content;

  const onSave = () => {
    save.mutate(
      { name, content: draft },
      {
        onSuccess: (resp) => setLastSavedAt(resp.skill.modified_at),
      },
    );
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSave();
      }}
      className="flex flex-col gap-3 rounded-lg border border-shadow-purple/60 bg-void-800/70 p-4"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold uppercase tracking-wider text-arise-violet-bright">
            {data.name}
          </h2>
          <p className="truncate text-xs text-soul-cyan/60">{data.path}</p>
        </div>
        <div className="flex items-center gap-3 text-xs">
          {save.isSuccess && !dirty ? (
            <span className="text-mana-green">
              Saved {(lastSavedAt ?? data.modified_at).slice(11, 19)}
            </span>
          ) : null}
          {save.isError ? (
            <span className="text-ember-red">
              {save.error instanceof Error ? save.error.message : "Save failed"}
            </span>
          ) : null}
          <button
            type="submit"
            disabled={!editable || !dirty || save.isPending}
            title={editable ? undefined : "Read-only — switch plugin_mode to local."}
            className="inline-flex items-center gap-1.5 rounded-md border border-arise-violet/60 bg-arise-violet/20 px-3 py-1.5 text-xs font-medium text-ghost-white transition hover:bg-arise-violet/30 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Save size={12} strokeWidth={2} />
            {save.isPending ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        readOnly={!editable}
        spellCheck={false}
        className="h-[520px] w-full resize-y rounded-md border border-shadow-purple/60 bg-void-900/70 p-3 font-mono text-xs leading-relaxed text-ghost-white focus:border-arise-violet focus:outline-none focus:ring-2 focus:ring-arise-violet/40"
      />
    </form>
  );
}
