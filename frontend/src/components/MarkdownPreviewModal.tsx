import { ExternalLink } from "lucide-react";
import { marked } from "marked";
import { useEffect, useMemo } from "react";
import { MOTION_CLASSES } from "~/lib/motion";

/**
 * Minimal shape every markdown-artifact source (RFC, plan, ...) exposes.
 *
 * The ``reason`` field surfaces the backend's explanation when ``ok===false``
 * (missing docs_repo, file-system error, etc.).
 */
export interface MarkdownArtifact {
  ok: boolean;
  exists: boolean;
  title: string;
  content: string;
  reason: string | null;
}

/**
 * Generic markdown preview modal shared between RFC + plan gates. Matches
 * the Claude Design bundle's ``PreviewModal``: centered card, eyebrow +
 * ``ENG-X · #PR`` meta in the header, "Close · esc" text link, scrollable
 * body, and a sticky footer with Back + Open-PR-on-GitHub + Open-in-editor.
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
  openEditor?: {
    mutate: () => void;
    isPending: boolean;
  };
  postRender?: (container: HTMLElement) => void;
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
    // Strip the artifact's leading ``# Title`` — we render a synthesised
    // ``ENG-X · Title`` H1 at the top of the body instead, so preserving
    // the original would duplicate it. Only clips when the markdown
    // *starts* with H1.
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

  const prNumber = extractPrNumber(prUrl);
  const combinedTitle = data?.title ? `${issueKey} · ${data.title}` : issueKey;

  return (
    <div
      data-markdown-preview-modal={kind}
      // biome-ignore lint/a11y/useSemanticElements: we style/animate the backdrop ourselves; native <dialog> would require a broader refactor
      role="dialog"
      aria-modal="true"
      aria-labelledby={`markdown-preview-title-${kind}`}
      onMouseDown={(e) => {
        // Click on the backdrop (but not the card) closes the modal — a
        // familiar convention for overlay dialogs.
        if (e.target === e.currentTarget) onClose();
      }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm sm:p-6"
    >
      <div
        className={`surface-raised relative flex w-full max-w-2xl flex-col overflow-hidden ${MOTION_CLASSES.runeIn}`}
        style={{ height: "min(85vh, 900px)" }}
      >
        {/* Header — eyebrow + ENG-X · #PR meta + "Close · esc" button.
         *  ``shrink-0`` so it never collapses; the body in between does
         *  the scrolling. */}
        <header className="flex shrink-0 items-start justify-between gap-4 px-6 pb-4 pt-5">
          <div className="flex items-start gap-3">
            <span
              aria-hidden="true"
              className="mt-[3px] inline-flex h-4 w-4 items-center justify-center rounded"
              style={{ color: "var(--color-arcane)" }}
            >
              <SigilMark />
            </span>
            <div>
              <p className="eyebrow">{label} preview</p>
              <p className="mt-1 font-mono text-[12px] text-ghost-dim">
                {issueKey}
                {prNumber ? (
                  <>
                    {" · "}
                    <span className="text-ghost">#{prNumber}</span>
                  </>
                ) : null}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="font-mono text-[11px] uppercase tracking-wider text-ghost-dim transition hover:text-arcane"
          >
            Close · <span className="kbd">esc</span>
          </button>
        </header>

        {/* ``min-h-0`` is the crucial bit — without it, flex children
         *  default to ``min-height: auto`` which prevents shrinking
         *  below their content size and the whole card overflows. */}
        <div
          className="scroll-arise min-h-0 flex-1 overflow-y-auto px-6 pb-4"
          data-markdown-preview-scroll
        >
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
            <>
              <h1
                id={`markdown-preview-title-${kind}`}
                className="mt-1 text-[22px] font-semibold leading-snug text-ghost"
                style={{ textWrap: "pretty" }}
              >
                {combinedTitle}
              </h1>
              <div
                // biome-ignore lint/security/noDangerouslySetInnerHtml: trusted source owned by user
                dangerouslySetInnerHTML={{ __html: html }}
                data-markdown-preview-body={kind}
                className="prose-rfc mt-3 max-w-none text-sm text-ghost/90"
              />
            </>
          )}
        </div>

        <footer className="flex shrink-0 items-center justify-between gap-3 border-t border-rune-line-strong bg-obsidian-raised/70 px-6 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-rune-line-strong bg-vault-soft px-3 py-1.5 text-xs font-medium text-ghost-dim transition hover:border-arcane/50 hover:text-arcane"
          >
            Back
          </button>
          <div className="flex items-center gap-2">
            {openEditor && data?.exists ? (
              <button
                type="button"
                onClick={() => openEditor.mutate()}
                disabled={openEditor.isPending}
                className="inline-flex items-center gap-1.5 rounded-md border border-arcane/50 bg-arcane/10 px-3 py-1.5 text-xs font-medium text-arcane transition hover:bg-arcane/20 disabled:opacity-50"
              >
                Open in editor
              </button>
            ) : null}
            {prUrl ? (
              <a
                href={prUrl}
                target="_blank"
                rel="noreferrer"
                data-preview-action="open-github"
                className="inline-flex items-center gap-1.5 rounded-md border border-arcane/50 bg-arcane/10 px-3 py-1.5 text-xs font-medium text-arcane transition hover:bg-arcane/20"
              >
                Open PR on GitHub
                <ExternalLink size={11} strokeWidth={2} />
              </a>
            ) : null}
          </div>
        </footer>
      </div>
    </div>
  );
}

/** Pull the PR number out of a canonical GitHub PR URL. Returns ``null``
 *  when the URL doesn't match the ``.../pull/<n>`` shape so the header
 *  safely hides the ``· #N`` meta. */
function extractPrNumber(prUrl: string | null | undefined): string | null {
  if (!prUrl) return null;
  const match = prUrl.match(/\/pull\/(\d+)(?:$|[/?#])/);
  return match?.[1] ?? null;
}

/** Tiny inline sigil used next to the header eyebrow. Purely decorative —
 *  the header text is the actual label for screen readers. */
function SigilMark() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true">
      <g fill="none" stroke="currentColor" strokeWidth={1}>
        <circle cx="12" cy="12" r="9" strokeDasharray="2 3" />
        <polygon points="12,5 19,16 5,16" />
        <circle cx="12" cy="12" r="1.5" fill="currentColor" />
      </g>
    </svg>
  );
}
