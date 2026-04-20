import { ChevronDown, ChevronRight, FileText } from "lucide-react";
import { marked } from "marked";
import { type ReactNode, useEffect, useMemo, useState } from "react";

/**
 * Minimal shape every markdown-artifact source (RFC, plan, ...) must expose.
 *
 * The ``reason`` field is used only when ``ok === false`` — it surfaces the
 * backend's explanation for why the doc/plan could not be read (missing
 * ``docs_repo``, file-system error, etc.). When ``exists === false`` and
 * ``ok === true`` it is optional; the wrapper components decide whether to
 * show a context-aware empty state (``emptyState`` slot below).
 */
export interface MarkdownArtifact {
  ok: boolean;
  exists: boolean;
  title: string;
  content: string;
  reason: string | null;
}

interface Props {
  /** Short label for the panel header, e.g. ``"RFC"`` or ``"Plan"``. */
  label: string;
  /** Stable id used for ``data-*`` test hooks (``"rfc"`` / ``"plan"``). */
  kind: string;
  /** React-query state. ``data`` is ``undefined`` while loading. */
  data: MarkdownArtifact | undefined;
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  /**
   * Optional "Open in editor" mutation hook. When provided, the panel shows
   * a button that calls ``onOpenEditor`` after a successful ``data.exists``.
   */
  openEditor?: {
    mutate: () => void;
    isPending: boolean;
  };
  /** Context-aware empty state (e.g. "agent is drafting the RFC"). */
  emptyState: ReactNode;
  /**
   * Called after the rendered HTML mounts in the DOM. Used by the RFC panel
   * to rewrite relative image paths to the API image endpoint; the plan
   * panel leaves this unset.
   */
  postRender?: (container: HTMLElement) => void;
  /**
   * Initial expanded state. Defaults to ``false`` (collapsed). The "Open in
   * editor" button stays visible when collapsed so the user never has to
   * expand just to launch their editor.
   */
  defaultExpanded?: boolean;
}

/**
 * Read-only markdown viewer shared between RFC + plan panels.
 *
 * Layout: header with collapse chevron + title + optional "Open in editor";
 * body that toggles between empty / loading / error / collapsed teaser /
 * full markdown. Rendering uses ``marked`` client-side — we own the input
 * so there's no sanitisation layer (same tradeoff as the old RfcPanel).
 *
 * Wrappers keep the kind-specific knowledge (``useRfc`` / ``usePlan``
 * hooks, empty-state copy, image rewriting) so this component stays free
 * of project vocabulary and can be reused for future artifact types.
 */
export function MarkdownArtifactPanel({
  label,
  kind,
  data,
  isLoading,
  isError,
  error,
  openEditor,
  emptyState,
  postRender,
  defaultExpanded = false,
}: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  const html = useMemo(() => {
    if (!data?.content) return "";
    return marked.parse(data.content, { gfm: true, breaks: false }) as string;
  }, [data?.content]);

  useEffect(() => {
    if (!html || !data?.exists || !expanded || !postRender) return;
    const container = document.querySelector<HTMLDivElement>(`[data-${kind}-body]`);
    if (!container) return;
    postRender(container);
  }, [html, data?.exists, expanded, postRender, kind]);

  const panelAttr = { [`data-${kind}-panel`]: true } as Record<string, boolean>;
  const toggleAttr = {
    [`data-${kind}-toggle`]: data?.exists ? (expanded ? "expanded" : "collapsed") : "disabled",
  } as Record<string, string>;
  const bodyAttr = { [`data-${kind}-body`]: true } as Record<string, boolean>;

  return (
    <section
      {...panelAttr}
      className="flex flex-col gap-4 rounded-lg border border-shadow-purple/60 bg-void-800/70 p-5"
    >
      <header className="flex flex-wrap items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => (data?.exists ? setExpanded((v) => !v) : undefined)}
          disabled={!data?.exists}
          {...toggleAttr}
          className="flex items-center gap-2 text-left disabled:cursor-default"
        >
          {data?.exists ? (
            expanded ? (
              <ChevronDown size={14} strokeWidth={2} className="text-arise-violet" />
            ) : (
              <ChevronRight size={14} strokeWidth={2} className="text-arise-violet" />
            )
          ) : (
            <FileText size={14} strokeWidth={2} className="text-arise-violet" />
          )}
          <h2 className="text-sm font-semibold uppercase tracking-wider text-arise-violet-bright">
            {label}
          </h2>
          {data?.exists ? <span className="text-xs text-soul-cyan/70">{data.title}</span> : null}
        </button>
        {data?.exists && openEditor ? (
          <div className="flex items-center gap-2 text-xs">
            <button
              type="button"
              onClick={() => openEditor.mutate()}
              disabled={openEditor.isPending}
              className="inline-flex items-center gap-1 rounded-md border border-arise-violet/50 bg-arise-violet/15 px-2 py-1 text-arise-violet-bright hover:bg-arise-violet/25 disabled:opacity-50"
            >
              Open in editor
            </button>
          </div>
        ) : null}
      </header>

      {isLoading ? (
        <p className="text-xs text-soul-cyan/70">Loading {label}…</p>
      ) : isError ? (
        <p className="text-xs text-ember-red">
          {error instanceof Error ? error.message : `Failed to load ${label}`}
        </p>
      ) : !data?.ok ? (
        <p className="text-xs text-amber-flame">{data?.reason ?? `${label} unavailable`}</p>
      ) : !data.exists ? (
        emptyState
      ) : expanded ? (
        <div
          // biome-ignore lint/security/noDangerouslySetInnerHtml: trusted source owned by user
          dangerouslySetInnerHTML={{ __html: html }}
          {...bodyAttr}
          className="prose-rfc max-w-none text-sm text-soul-cyan/90"
        />
      ) : (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="text-left text-xs text-soul-cyan/60 hover:text-ghost-white"
        >
          Click to expand the full {label.toLowerCase()} (or use "Open in editor").
        </button>
      )}
    </section>
  );
}
