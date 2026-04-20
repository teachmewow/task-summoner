import { X } from "lucide-react";
import { marked } from "marked";
import { useEffect, useMemo } from "react";
import { useRfc } from "~/lib/rfcs";

/**
 * Lightweight modal that shows the current RFC without leaving the gate card.
 *
 * Product intent: when a human is reviewing a doc gate they want to read the
 * doc fast — not scroll past the timeline to find the collapsed RfcPanel.
 * The modal reuses the existing ``useRfc`` query (cache hit if the page
 * already loaded it) and the same ``marked`` pipeline as ``RfcPanel``.
 * Close via the explicit X button or the Escape key; no backdrop-click close
 * to stay consistent with ``RequestChangesModal`` and keep accessibility
 * lint rules happy.
 */
interface Props {
  issueKey: string;
  open: boolean;
  onClose: () => void;
}

export function RfcPreviewModal({ issueKey, open, onClose }: Props) {
  const { data, isLoading, isError, error } = useRfc(open ? issueKey : null);

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
      data-rfc-preview-modal
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 p-6"
    >
      <div className="relative mt-6 w-full max-w-3xl rounded-lg border border-shadow-purple/60 bg-void-900 p-6 shadow-2xl">
        <header className="mb-4 flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-wider text-arise-violet-bright">RFC preview</p>
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
          <p className="text-sm text-soul-cyan/70">Loading RFC…</p>
        ) : isError ? (
          <p className="text-sm text-ember-red">
            {error instanceof Error ? error.message : "Failed to load RFC"}
          </p>
        ) : !data?.ok ? (
          <p className="text-sm text-amber-flame">{data?.reason ?? "docs_repo unavailable"}</p>
        ) : !data.exists ? (
          <p className="text-sm text-soul-cyan/70">No RFC drafted yet for {issueKey}.</p>
        ) : (
          <div
            // biome-ignore lint/security/noDangerouslySetInnerHtml: owned docs repo
            dangerouslySetInnerHTML={{ __html: html }}
            data-rfc-preview-body
            className="prose-rfc max-w-none text-sm text-soul-cyan/90"
          />
        )}
      </div>
    </div>
  );
}
