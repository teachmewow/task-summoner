import { X } from "lucide-react";
import { marked } from "marked";
import { useEffect, useMemo } from "react";
import type { MarkdownArtifact } from "./MarkdownArtifactPanel";

/**
 * Generic markdown preview modal shared between RFC + plan gates.
 *
 * Opens to the rendered markdown of whatever artifact the caller passes in.
 * Wrappers (``RfcPreviewModal`` / ``PlanPreviewModal``) bind the appropriate
 * react-query hook + label; this component stays artifact-agnostic so new
 * gate types can reuse it without changing modal-layout code.
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
}: Props) {
  const html = useMemo(() => {
    if (!data?.content) return "";
    return marked.parse(data.content, { gfm: true, breaks: false }) as string;
  }, [data?.content]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      data-markdown-preview-modal={label.toLowerCase()}
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 p-6"
    >
      <div className="relative mt-6 w-full max-w-3xl rounded-lg border border-shadow-purple/60 bg-void-900 p-6 shadow-2xl">
        <header className="mb-4 flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-wider text-arise-violet-bright">
              {label} preview
            </p>
            <h2 className="mt-1 text-lg font-semibold text-ghost-white">
              {data?.title || issueKey}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close preview"
            className="rounded-md border border-shadow-purple/60 bg-void-800 p-1.5 text-soul-cyan transition hover:border-arise-violet/50 hover:text-ghost-white"
          >
            <X size={14} strokeWidth={2} />
          </button>
        </header>

        {isLoading ? (
          <p className="text-sm text-soul-cyan/70">Loading {label}…</p>
        ) : isError ? (
          <p className="text-sm text-ember-red">
            {error instanceof Error ? error.message : `Failed to load ${label}`}
          </p>
        ) : !data?.ok ? (
          <p className="text-sm text-amber-flame">{data?.reason ?? `${label} unavailable`}</p>
        ) : !data.exists ? (
          <p className="text-sm text-soul-cyan/70">
            No {label.toLowerCase()} drafted yet for {issueKey}.
          </p>
        ) : (
          <div
            // biome-ignore lint/security/noDangerouslySetInnerHtml: trusted source owned by user
            dangerouslySetInnerHTML={{ __html: html }}
            data-markdown-preview-body={label.toLowerCase()}
            className="prose-rfc max-w-none text-sm text-soul-cyan/90"
          />
        )}
      </div>
    </div>
  );
}
