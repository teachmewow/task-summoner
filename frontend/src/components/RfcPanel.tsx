import { ChevronDown, ChevronRight, ExternalLink, FileText, Sparkles, X } from "lucide-react";
import { marked } from "marked";
import { useEffect, useMemo, useState } from "react";
import { rfcImageUrl, useOpenRfc, useRfc } from "~/lib/rfcs";

/**
 * Read-only RFC render panel (ENG-98 + ENG-121).
 *
 * We render markdown client-side via ``marked``. The raw HTML ends up in a
 * scoped container — it's the same docs repo the user owns, not arbitrary
 * web content, so sanitisation is out of scope for v0 (the threat model is
 * the user opening their own markdown).
 *
 * Images whose ``src`` is a bare filename are rewritten to the API image
 * endpoint so they render offline; external URLs (``http://``) pass through.
 *
 * Empty state messaging (ENG-121): when the panel lives under the issue
 * detail page's activity timeline, the "Run /create-design-doc" CTA is
 * misleading — the agent is the one drafting the doc. Accepting the
 * orchestrator state as a prop lets us tailor the copy: "agent is drafting"
 * during CREATING_DOC, "no doc required" post-classifier, plain "no RFC"
 * otherwise.
 */
interface Props {
  issueKey: string;
  /**
   * Orchestrator state — used to pick a context-aware empty-state message.
   * Undefined/null is treated as "no context": we render the generic empty
   * state that suggests opening the docs repo.
   */
  orchestratorState?: string | null;
  /** Optional callback fired when the user clicks the CTA on the empty state. */
  onSummonCreateDesignDoc?: () => void;
}

/** States during or after which the RFC should exist or be in the works. */
const RFC_ACTIVE_STATES = new Set([
  "CREATING_DOC",
  "WAITING_DOC_REVIEW",
  "IMPROVING_DOC",
  "PLANNING",
  "WAITING_PLAN_REVIEW",
  "IMPLEMENTING",
  "WAITING_MR_REVIEW",
  "FIXING_MR",
  "DONE",
]);

/** Pre-doc states where the user shouldn't be surprised there's no RFC yet. */
const RFC_PENDING_STATES = new Set(["QUEUED", "CHECKING_DOC"]);

export function RfcPanel({ issueKey, orchestratorState, onSummonCreateDesignDoc }: Props) {
  const { data, isLoading, isError, error } = useRfc(issueKey);
  const open = useOpenRfc(issueKey);
  const [zoomed, setZoomed] = useState<string | null>(null);
  // Collapsed by default once the RFC exists — most users glance at the title,
  // click the gate buttons, and don't want the entire doc expanded every time
  // they open the issue page. Empty / drafting / error states stay inline so
  // the user isn't guessing why the panel is blank.
  const [expanded, setExpanded] = useState(false);

  const html = useMemo(() => {
    if (!data?.content) return "";
    // ``marked.parse`` is synchronous by default with the options we use.
    return marked.parse(data.content, { gfm: true, breaks: false }) as string;
  }, [data?.content]);

  // Rewrite <img src="impact.png"> to the API route after render. Re-runs on
  // expand so the hook finds the `[data-rfc-body]` container that only mounts
  // after the user clicks to expand the collapsed RFC.
  useEffect(() => {
    if (!html || !data?.exists || !expanded) return;
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
  }, [html, data?.exists, issueKey, expanded]);

  return (
    <section
      data-rfc-panel
      className="flex flex-col gap-4 rounded-lg border border-shadow-purple/60 bg-void-800/70 p-5"
    >
      <header className="flex flex-wrap items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => (data?.exists ? setExpanded((v) => !v) : undefined)}
          disabled={!data?.exists}
          data-rfc-toggle={data?.exists ? (expanded ? "expanded" : "collapsed") : "disabled"}
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
            RFC
          </h2>
          {data?.exists ? <span className="text-xs text-soul-cyan/70">{data.title}</span> : null}
        </button>
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
          orchestratorState={orchestratorState ?? null}
          {...(onSummonCreateDesignDoc ? { onSummon: onSummonCreateDesignDoc } : {})}
          reason={data.reason}
        />
      ) : expanded ? (
        <div
          // biome-ignore lint/security/noDangerouslySetInnerHtml: owned docs repo
          dangerouslySetInnerHTML={{ __html: html }}
          data-rfc-body
          className="prose-rfc max-w-none text-sm text-soul-cyan/90"
        />
      ) : (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="text-left text-xs text-soul-cyan/60 hover:text-ghost-white"
        >
          Click to expand the full doc (or use "Open in editor").
        </button>
      )}

      {zoomed ? <ImageModal src={zoomed} onClose={() => setZoomed(null)} /> : null}
    </section>
  );
}

function EmptyState({
  issueKey,
  orchestratorState,
  onSummon,
  reason,
}: {
  issueKey: string;
  orchestratorState: string | null;
  onSummon?: () => void;
  reason: string | null;
}) {
  // When we know what the orchestrator is doing, tell the user — nagging them
  // to "run /create-design-doc" while the agent is already drafting the doc
  // is strictly worse than saying nothing.
  if (orchestratorState && RFC_ACTIVE_STATES.has(orchestratorState)) {
    return (
      <div
        data-rfc-empty="drafting"
        className="flex flex-col items-start gap-1 rounded-md border border-shadow-purple/60 bg-void-900/40 p-4 text-sm text-soul-cyan/80"
      >
        <p className="font-medium text-ghost-white">Agent is drafting the RFC.</p>
        <p className="text-xs text-soul-cyan/70">
          It will appear here when ready — watch live progress in the Agent activity timeline above.
        </p>
      </div>
    );
  }

  if (orchestratorState && RFC_PENDING_STATES.has(orchestratorState)) {
    return (
      <div
        data-rfc-empty="pending"
        className="flex flex-col items-start gap-1 rounded-md border border-shadow-purple/60 bg-void-900/40 p-4 text-sm text-soul-cyan/80"
      >
        <p>The orchestrator is still deciding whether this ticket needs a design doc.</p>
        <p className="text-xs text-soul-cyan/70">
          Once the classifier has run, this panel will either show the RFC or confirm none was
          required.
        </p>
      </div>
    );
  }

  return (
    <div
      data-rfc-empty="generic"
      className="flex flex-col items-start gap-2 rounded-md border border-shadow-purple/60 bg-void-900/40 p-4 text-sm text-soul-cyan/80"
    >
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
          If this ticket needs a design doc, the orchestrator will author it the next time it picks
          up the issue.
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
