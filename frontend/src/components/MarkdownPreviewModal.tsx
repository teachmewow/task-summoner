import { ExternalLink, X } from "lucide-react";
import { marked } from "marked";
import { useEffect, useMemo } from "react";
import { MOTION_CLASSES } from "~/lib/motion";

/**
 * Minimal shape every markdown-artifact source (RFC, plan, ...) exposes.
 *
 * The ``reason`` field surfaces the backend's explanation when ``ok===false``
 * (missing docs_repo, file-system error, etc.). Declared here rather than on
 * a dedicated types file because this modal is the only consumer now that
 * the standalone panel components are gone.
 */
export interface MarkdownArtifact {
  ok: boolean;
  exists: boolean;
  title: string;
  content: string;
  reason: string | null;
}

/**
 * Generic markdown preview modal shared between RFC + plan gates.
 *
 * Wrappers (``RfcPreviewModal`` / ``PlanPreviewModal``) bind the react-query
 * hook + label; this stays artifact-agnostic so new gate types plug in with
 * a hook and an optional ``postRender`` / ``openEditor`` pair.
 */
interface Props {
  issueKey: string;
  label: string;
  open: boolean;
  onClose: () => void;
  data: MarkdownArtifact | undefined;
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  /**
   * Optional "Open in editor" mutation. When provided, the modal header
   * shows an extra button that fires the caller's ``onOpenEditor`` — used
   * by the RFC/plan modals to launch the user's editor on the artifact.
   */
  openEditor?: {
    mutate: () => void;
    isPending: boolean;
  };
  /**
   * Called after the rendered HTML mounts. Only the RFC wrapper uses this
   * to rewrite relative image paths to the API image endpoint.
   */
  postRender?: (container: HTMLElement) => void;
  /**
   * Optional PR URL. When provided, the modal header includes a
   * "View PR on GitHub" link — reviewers sometimes want to jump to the
   * diff after reading the doc.
   */
  prUrl?: string | null;
}

export function MarkdownPreviewModal({
  issueKey,
  label,
  open,
  onClose,
  data,
  isLoading,
  isError,
  error,
  openEditor,
  postRender,
  prUrl,
}: Props) {
  const html = useMemo(() => {
    if (!data?.content) return "";
    // Drop the artifact's leading ``# Title`` when we're already showing
    // that title in the modal header — otherwise it renders twice. We
    // only strip when the markdown *starts* with an H1 (after optional
    // blank lines); any other prose stays untouched.
    const body = data.content.replace(/^\s*#[^\n]*\n+/, "");
    return marked.parse(body, { gfm: true, breaks: false }) as string;
  }, [data?.content]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const kind = label.toLowerCase();
  useEffect(() => {
    if (!open || !html || !data?.exists || !postRender) return;
    const container = document.querySelector<HTMLDivElement>(
      `[data-markdown-preview-body="${kind}"]`,
    );
    if (!container) return;
    postRender(container);
  }, [open, html, data?.exists, postRender, kind]);

  if (!open) return null;

  return (
    <div
      data-markdown-preview-modal={kind}
      // biome-ignore lint/a11y/useSemanticElements: we style/animate the backdrop ourselves; native <dialog> would require a broader refactor
      role="dialog"
      aria-modal="true"
      aria-labelledby={`markdown-preview-title-${kind}`}
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 p-6 backdrop-blur-sm"
    >
      <div
        className={`relative mt-6 w-full max-w-3xl rounded-2xl border border-rune-line-strong bg-obsidian-raised p-6 glow-arcane-soft ${MOTION_CLASSES.runeIn}`}
      >
        <header className="mb-4 flex items-start justify-between gap-4">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-wider text-arcane">
              {label} preview
            </p>
            <h2
              id={`markdown-preview-title-${kind}`}
              className="mt-1 text-lg font-semibold text-ghost"
            >
              {data?.title || issueKey}
            </h2>
          </div>
          <div className="flex items-center gap-2">
            {prUrl ? (
              <a
                href={prUrl}
                target="_blank"
                rel="noreferrer"
                data-preview-action="open-github"
                className="inline-flex items-center gap-1 rounded-md border border-rune-line-strong bg-vault-soft px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-ghost-dim transition hover:border-arcane/50 hover:text-arcane"
              >
                Open in GitHub
                <ExternalLink size={10} strokeWidth={2} />
              </a>
            ) : null}
            {openEditor && data?.exists ? (
              <button
                type="button"
                onClick={() => openEditor.mutate()}
                disabled={openEditor.isPending}
                className="inline-flex items-center gap-1 rounded-md border border-arcane/50 bg-arcane/10 px-2 py-1 text-xs font-medium text-arcane transition hover:bg-arcane/20 disabled:opacity-50"
              >
                Open in editor
              </button>
            ) : null}
            <button
              type="button"
              onClick={onClose}
              aria-label="Close preview"
              className="rounded-md border border-rune-line-strong bg-vault-soft p-1.5 text-ghost-dim transition hover:border-arcane/50 hover:text-arcane"
            >
              <X size={14} strokeWidth={2} />
            </button>
          </div>
        </header>

        {isLoading ? (
          <p className="text-sm text-ghost-dim">Loading {label}…</p>
        ) : isError ? (
          <p className="text-sm text-blood">
            {error instanceof Error ? error.message : `Failed to load ${label}`}
          </p>
        ) : !data?.ok ? (
          <p className="text-sm text-ember">{data?.reason ?? `${label} unavailable`}</p>
        ) : !data.exists ? (
          <p className="text-sm text-ghost-dim">
            No {kind} drafted yet for {issueKey}.
          </p>
        ) : (
          <div
            // biome-ignore lint/security/noDangerouslySetInnerHtml: trusted source owned by user
            dangerouslySetInnerHTML={{ __html: html }}
            data-markdown-preview-body={kind}
            className="prose-rfc max-w-none text-sm text-ghost/90"
          />
        )}
      </div>
    </div>
  );
}
