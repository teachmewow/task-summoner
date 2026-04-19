import { ExternalLink, FileText, Sparkles, X } from "lucide-react";
import { marked } from "marked";
import { useEffect, useMemo, useState } from "react";
import { rfcImageUrl, useOpenRfc, useRfc } from "~/lib/rfcs";

/**
 * Read-only RFC render panel (ENG-98).
 *
 * We render markdown client-side via ``marked``. The raw HTML ends up in a
 * scoped container — it's the same docs repo the user owns, not arbitrary
 * web content, so sanitisation is out of scope for v0 (the threat model is
 * the user opening their own markdown).
 *
 * Images whose ``src`` is a bare filename are rewritten to the API image
 * endpoint so they render offline; external URLs (``http://``) pass through.
 */
interface Props {
  issueKey: string;
  /** Optional callback fired when the user clicks the CTA on the empty state. */
  onSummonCreateDesignDoc?: () => void;
}

export function RfcPanel({ issueKey, onSummonCreateDesignDoc }: Props) {
  const { data, isLoading, isError, error } = useRfc(issueKey);
  const open = useOpenRfc(issueKey);
  const [zoomed, setZoomed] = useState<string | null>(null);

  const html = useMemo(() => {
    if (!data?.content) return "";
    // ``marked.parse`` is synchronous by default with the options we use.
    return marked.parse(data.content, { gfm: true, breaks: false }) as string;
  }, [data?.content]);

  // Rewrite <img src="impact.png"> to the API route after render.
  useEffect(() => {
    if (!html || !data?.exists) return;
    const container = document.querySelector<HTMLDivElement>("[data-rfc-body]");
    if (!container) return;
    const imgs = container.querySelectorAll("img");
    for (const img of Array.from(imgs)) {
      const src = img.getAttribute("src") ?? "";
      if (/^https?:/i.test(src) || src.startsWith("/")) continue;
      img.setAttribute("src", rfcImageUrl(issueKey, src));
      img.setAttribute("loading", "lazy");
      img.classList.add("cursor-zoom-in", "rounded-md", "border", "border-shadow-purple/50");
      img.addEventListener("click", () => setZoomed(img.getAttribute("src")));
    }
  }, [html, data?.exists, issueKey]);

  return (
    <section
      data-rfc-panel
      className="flex flex-col gap-4 rounded-lg border border-shadow-purple/60 bg-void-800/70 p-5"
    >
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <FileText size={14} strokeWidth={2} className="text-arise-violet" />
          <h2 className="text-sm font-semibold uppercase tracking-wider text-arise-violet-bright">
            RFC
          </h2>
          {data?.exists ? <span className="text-xs text-soul-cyan/70">{data.title}</span> : null}
        </div>
        {data?.exists ? (
          <div className="flex items-center gap-2 text-xs">
            <button
              type="button"
              onClick={() => open.mutate(undefined)}
              disabled={open.isPending}
              className="inline-flex items-center gap-1 rounded-md border border-arise-violet/50 bg-arise-violet/15 px-2 py-1 text-arise-violet-bright hover:bg-arise-violet/25 disabled:opacity-50"
            >
              Open in editor
            </button>
          </div>
        ) : null}
      </header>

      {isLoading ? (
        <p className="text-xs text-soul-cyan/70">Loading RFC…</p>
      ) : isError ? (
        <p className="text-xs text-ember-red">
          {error instanceof Error ? error.message : "Failed to load RFC"}
        </p>
      ) : !data?.ok ? (
        <p className="text-xs text-amber-flame">{data?.reason ?? "docs_repo unavailable"}</p>
      ) : !data.exists ? (
        <EmptyState
          issueKey={issueKey}
          {...(onSummonCreateDesignDoc ? { onSummon: onSummonCreateDesignDoc } : {})}
          reason={data.reason}
        />
      ) : (
        <div
          // biome-ignore lint/security/noDangerouslySetInnerHtml: owned docs repo
          dangerouslySetInnerHTML={{ __html: html }}
          data-rfc-body
          className="prose-rfc max-w-none text-sm text-soul-cyan/90"
        />
      )}

      {zoomed ? <ImageModal src={zoomed} onClose={() => setZoomed(null)} /> : null}
    </section>
  );
}

function EmptyState({
  issueKey,
  onSummon,
  reason,
}: {
  issueKey: string;
  onSummon?: () => void;
  reason: string | null;
}) {
  return (
    <div className="flex flex-col items-start gap-2 rounded-md border border-shadow-purple/60 bg-void-900/40 p-4 text-sm text-soul-cyan/80">
      <p>
        No RFC found for <code className="text-ghost-white/90">{issueKey}</code>.
      </p>
      {reason ? <p className="text-xs text-soul-cyan/60">{reason}</p> : null}
      {onSummon ? (
        <button
          type="button"
          onClick={onSummon}
          className="inline-flex items-center gap-1.5 rounded-md border border-arise-violet/50 bg-arise-violet/15 px-3 py-1.5 text-xs font-medium text-arise-violet-bright transition hover:bg-arise-violet/25"
        >
          <Sparkles size={12} strokeWidth={2} />
          Summon create-design-doc
        </button>
      ) : (
        <p className="text-xs text-soul-cyan/60">
          Run <code className="text-ghost-white/90">/create-design-doc {issueKey}</code> in your
          editor to author one.
        </p>
      )}
    </div>
  );
}

function ImageModal({ src, onClose }: { src: string; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-6"
      aria-modal="true"
      data-image-modal
    >
      <button
        type="button"
        onClick={onClose}
        aria-label="Close image"
        className="absolute inset-0 h-full w-full cursor-zoom-out"
      />
      <button
        type="button"
        onClick={onClose}
        aria-label="Close"
        className="absolute right-4 top-4 z-10 rounded-full bg-void-900/80 p-2 text-ghost-white"
      >
        <X size={16} strokeWidth={2} />
      </button>
      <img
        src={src}
        alt="RFC attachment, full size"
        className="z-10 max-h-[90vh] max-w-[90vw] rounded-md object-contain"
      />
      <a
        href={src}
        target="_blank"
        rel="noreferrer"
        onClick={(e) => e.stopPropagation()}
        className="absolute bottom-4 right-4 z-10 inline-flex items-center gap-1 rounded-md bg-void-900/80 px-2 py-1 text-xs text-ghost-white"
      >
        Open raw
        <ExternalLink size={10} strokeWidth={2} />
      </a>
    </div>
  );
}
