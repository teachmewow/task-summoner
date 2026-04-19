import { BookOpen, ExternalLink, FileText, Filter, RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import {
  type DecisionSummary,
  useDecisions,
  useOpenDecision,
  useRefreshDecisions,
} from "~/lib/decisions";

interface Props {
  /** When provided, the sidebar renders inside a fixed-width column. */
  limit?: number;
}

export function DecisionsSidebar({ limit = 10 }: Props) {
  const { data, isLoading, isError, error } = useDecisions(limit);
  const refresh = useRefreshDecisions();
  const open = useOpenDecision();
  const [tagFilter, setTagFilter] = useState<string | null>(null);

  const allTags = useMemo(() => {
    if (!data?.decisions) return [] as string[];
    const set = new Set<string>();
    for (const d of data.decisions) for (const t of d.tags) set.add(t);
    return Array.from(set).sort();
  }, [data]);

  const filtered = useMemo(() => {
    if (!data?.decisions) return [] as DecisionSummary[];
    if (!tagFilter) return data.decisions;
    return data.decisions.filter((d) => d.tags.includes(tagFilter));
  }, [data, tagFilter]);

  return (
    <aside
      data-sidebar="decisions"
      className="flex flex-col gap-3 rounded-lg border border-shadow-purple/60 bg-void-800/70 p-4"
    >
      <header className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <BookOpen size={14} strokeWidth={2} className="text-arise-violet" />
          <h3 className="text-sm font-semibold uppercase tracking-wider text-arise-violet-bright">
            Recent decisions
          </h3>
        </div>
        <button
          type="button"
          onClick={() => refresh()}
          className="inline-flex items-center gap-1 rounded-md border border-shadow-purple/60 bg-void-900/60 px-2 py-1 text-xs text-soul-cyan transition hover:border-arise-violet/50 hover:text-ghost-white"
          title="Refresh from disk"
        >
          <RefreshCw size={10} strokeWidth={2} />
          Refresh
        </button>
      </header>

      {isLoading ? (
        <p className="text-xs text-soul-cyan/70">Loading decisions…</p>
      ) : isError ? (
        <p className="text-xs text-ember-red">
          {error instanceof Error ? error.message : "Failed to load decisions"}
        </p>
      ) : !data?.configured ? (
        <div className="rounded-md border border-amber-flame/40 bg-amber-flame/10 p-3 text-xs text-amber-flame">
          <p>
            {data?.reason ??
              "docs_repo is not configured. Run `task-summoner config set docs_repo <path>`."}
          </p>
          <a
            href={data?.template_readme_url}
            target="_blank"
            rel="noreferrer"
            className="mt-2 inline-flex items-center gap-1 text-amber-flame hover:text-ghost-white"
          >
            Use the template
            <ExternalLink size={10} strokeWidth={2} />
          </a>
        </div>
      ) : !data.ok ? (
        <p className="text-xs text-ember-red">{data.reason}</p>
      ) : data.decisions.length === 0 ? (
        <div className="rounded-md border border-shadow-purple/60 bg-void-900/40 p-3 text-xs text-soul-cyan/80">
          <p className="mb-2">No decisions yet — create your first with the RFC template.</p>
          <a
            href={data.template_readme_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-arise-violet-bright hover:text-ghost-white"
          >
            Template README
            <ExternalLink size={10} strokeWidth={2} />
          </a>
        </div>
      ) : (
        <>
          {allTags.length > 0 ? (
            <div className="flex flex-wrap items-center gap-1 text-xs" data-tag-filters>
              <Filter size={11} strokeWidth={2} className="text-soul-cyan/70" />
              <button
                type="button"
                onClick={() => setTagFilter(null)}
                className={[
                  "rounded-full border px-2 py-0.5",
                  tagFilter === null
                    ? "border-arise-violet/60 bg-arise-violet/20 text-ghost-white"
                    : "border-shadow-purple/60 bg-void-900/40 text-soul-cyan hover:text-ghost-white",
                ].join(" ")}
              >
                all
              </button>
              {allTags.map((tag) => (
                <button
                  key={tag}
                  type="button"
                  onClick={() => setTagFilter(tag === tagFilter ? null : tag)}
                  className={[
                    "rounded-full border px-2 py-0.5",
                    tagFilter === tag
                      ? "border-arise-violet/60 bg-arise-violet/20 text-ghost-white"
                      : "border-shadow-purple/60 bg-void-900/40 text-soul-cyan hover:text-ghost-white",
                  ].join(" ")}
                >
                  {tag}
                </button>
              ))}
            </div>
          ) : null}

          <ul className="scroll-arise flex max-h-[520px] flex-col gap-2 overflow-y-auto pr-1">
            {filtered.map((d) => (
              <li
                key={d.path}
                className="rounded-md border border-shadow-purple/50 bg-void-900/40 p-3"
                data-decision
              >
                <div className="flex items-start gap-2">
                  <FileText size={12} strokeWidth={2} className="mt-1 shrink-0 text-arise-violet" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-ghost-white">{d.title}</p>
                    <p className="text-[10px] text-soul-cyan/60">
                      {d.committed_at ? d.committed_at.slice(0, 10) : "uncommitted"} · {d.filename}
                    </p>
                  </div>
                </div>
                {d.summary ? (
                  <p className="mt-1 line-clamp-3 text-xs text-soul-cyan/80">{d.summary}</p>
                ) : null}
                {d.tags.length > 0 ? (
                  <p className="mt-1 flex flex-wrap gap-1">
                    {d.tags.map((t) => (
                      <span
                        key={t}
                        className="rounded-full border border-arise-violet/30 bg-arise-violet/5 px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-arise-violet-bright"
                      >
                        {t}
                      </span>
                    ))}
                  </p>
                ) : null}
                <div className="mt-2 flex items-center gap-2 text-[10px]">
                  <button
                    type="button"
                    onClick={() => open.mutate(d.path)}
                    disabled={open.isPending}
                    className="inline-flex items-center gap-1 rounded-md border border-arise-violet/50 bg-arise-violet/15 px-2 py-0.5 text-arise-violet-bright hover:bg-arise-violet/25 disabled:opacity-50"
                  >
                    Open in editor
                  </button>
                  <a
                    href={d.path}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-soul-cyan/70 hover:text-ghost-white"
                    title={d.relative_path}
                  >
                    file://
                    <ExternalLink size={9} strokeWidth={2} />
                  </a>
                </div>
              </li>
            ))}
          </ul>
          {open.isError ? (
            <p className="text-xs text-ember-red">
              {open.error instanceof Error ? open.error.message : "Open failed"}
            </p>
          ) : null}
        </>
      )}
    </aside>
  );
}
