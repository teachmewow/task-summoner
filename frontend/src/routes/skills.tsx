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

  if (isLoading) return <p className="text-ghost/80">Loading skills…</p>;
  if (isError || !data) {
    return (
      <section className="space-y-2">
        <h1 className="text-2xl font-semibold text-ghost">Skills Editor</h1>
        <p className="text-blood">Couldn't load skills. Configure Task Summoner first.</p>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-3xl font-semibold text-ghost">Skills Editor</h1>
        <p className="text-ghost/80">
          {data.plugin_mode === "local" ? "Local plugin" : "Installed plugin"} ·{" "}
          <code className="text-ghost/90">
            {data.resolved_from || data.plugin_path || "unresolved"}
          </code>
        </p>
        {data.reason ? <ReadOnlyNotice reason={data.reason} /> : null}
      </header>

      {data.skills.length === 0 ? (
        <p className="text-ghost-dim">No SKILL.md files found under the plugin path.</p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
          <SkillList skills={data.skills} selected={selected} onSelect={setSelected} />
          {selected ? (
            <Editor name={selected} editable={data.editable} />
          ) : (
            <div className="rounded-lg border border-rune-line-strong bg-vault-soft p-6 text-sm text-ghost-dim">
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
    <div className="flex items-start gap-2 rounded-md border border-ember/40 bg-ember/10 px-3 py-2 text-sm text-ember">
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
    <ul className="flex max-h-[600px] flex-col gap-1 overflow-y-auto rounded-lg border border-rune-line-strong bg-vault-soft p-2">
      {skills.map((s) => (
        <li key={s.name}>
          <button
            type="button"
            onClick={() => onSelect(s.name)}
            className={[
              "flex w-full items-start gap-2 rounded-md px-3 py-2 text-left transition",
              selected === s.name
                ? "bg-arcane/20 text-ghost shadow-[0_0_0_1px_var(--color-arcane)]"
                : "text-ghost/85 hover:bg-vault hover:text-ghost",
            ].join(" ")}
          >
            <FileText size={14} strokeWidth={2} className="mt-1 shrink-0 text-arcane" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">{s.name}</span>
              <span className="block truncate text-xs text-ghost-dimmer">
                {s.description || "—"}
              </span>
            </span>
            {s.user_invocable ? (
              <span className="mt-0.5 rounded-full border border-arcane/40 bg-arcane/10 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wider text-arcane">
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

  if (isLoading) return <p className="text-ghost/80">Loading skill…</p>;
  if (isError || !data) {
    return <p className="text-blood">Failed to load skill.</p>;
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
      className="flex flex-col gap-3 rounded-lg border border-rune-line-strong bg-vault-soft p-4"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold uppercase tracking-wider text-arcane">
            {data.name}
          </h2>
          <p className="truncate text-xs text-ghost-dimmer">{data.path}</p>
        </div>
        <div className="flex items-center gap-3 text-xs">
          {save.isSuccess && !dirty ? (
            <span className="text-phase-done">
              Saved {(lastSavedAt ?? data.modified_at).slice(11, 19)}
            </span>
          ) : null}
          {save.isError ? (
            <span className="text-blood">
              {save.error instanceof Error ? save.error.message : "Save failed"}
            </span>
          ) : null}
          <button
            type="submit"
            disabled={!editable || !dirty || save.isPending}
            title={editable ? undefined : "Read-only — switch plugin_mode to local."}
            className="inline-flex items-center gap-1.5 rounded-md border border-arcane/60 bg-arcane/20 px-3 py-1.5 text-xs font-medium text-ghost transition hover:bg-arcane/30 disabled:cursor-not-allowed disabled:opacity-40"
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
        className="h-[520px] w-full resize-y rounded-md border border-rune-line-strong bg-vault p-3 font-mono text-xs leading-relaxed text-ghost focus:border-arcane focus:outline-none focus:ring-2 focus:ring-arcane/40"
      />
    </form>
  );
}
