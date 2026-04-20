import { ExternalLink, Sparkles, X } from "lucide-react";
import { useCallback, useState } from "react";
import { rfcImageUrl, useOpenRfc, useRfc } from "~/lib/rfcs";
import { MarkdownArtifactPanel } from "./MarkdownArtifactPanel";

/**
 * Thin wrapper around ``MarkdownArtifactPanel`` for the RFC artifact.
 *
 * The only RFC-specific behaviour here is:
 *  - ``useRfc`` hook (docs repo).
 *  - Image rewriting (``rfc_image_url``) + an ImageModal for zoom-in.
 *  - Context-aware empty state tied to the orchestrator lifecycle.
 *
 * Everything else lives in ``MarkdownArtifactPanel`` so plan.md and future
 * artifacts (implementation report, scrape logs, ...) can reuse the same
 * collapse / loading / empty / expanded rendering path.
 */
interface Props {
  issueKey: string;
  /**
   * Orchestrator state — used to pick a context-aware empty-state message.
   * Undefined/null renders the generic "No RFC found" copy.
   */
  orchestratorState?: string | null;
  /** Optional callback fired when the user clicks the CTA on the empty state. */
  onSummonCreateDesignDoc?: () => void;
}

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

const RFC_PENDING_STATES = new Set(["QUEUED", "CHECKING_DOC"]);

export function RfcPanel({ issueKey, orchestratorState, onSummonCreateDesignDoc }: Props) {
  const query = useRfc(issueKey);
  const openMutation = useOpenRfc(issueKey);
  const [zoomed, setZoomed] = useState<string | null>(null);

  // Rewrite <img src="impact.png"> to the API image route + wire zoom.
  const postRender = useCallback(
    (container: HTMLElement) => {
      const imgs = container.querySelectorAll("img");
      for (const img of Array.from(imgs)) {
        const src = img.getAttribute("src") ?? "";
        if (/^https?:/i.test(src) || src.startsWith("/")) continue;
        img.setAttribute("src", rfcImageUrl(issueKey, src));
        img.setAttribute("loading", "lazy");
        img.classList.add("cursor-zoom-in", "rounded-md", "border", "border-shadow-purple/50");
        img.addEventListener("click", () => setZoomed(img.getAttribute("src")));
      }
    },
    [issueKey],
  );

  const emptyState =
    orchestratorState && RFC_ACTIVE_STATES.has(orchestratorState) ? (
      <Draft label="Agent is drafting the RFC." hint="timeline" />
    ) : orchestratorState && RFC_PENDING_STATES.has(orchestratorState) ? (
      <PendingClassifier />
    ) : (
      <NoRfc
        issueKey={issueKey}
        reason={query.data?.reason ?? null}
        {...(onSummonCreateDesignDoc ? { onSummon: onSummonCreateDesignDoc } : {})}
      />
    );

  return (
    <>
      <MarkdownArtifactPanel
        label="RFC"
        kind="rfc"
        data={query.data}
        isLoading={query.isLoading}
        isError={query.isError}
        error={query.error}
        openEditor={{
          mutate: () => openMutation.mutate(undefined),
          isPending: openMutation.isPending,
        }}
        emptyState={emptyState}
        postRender={postRender}
      />
      {zoomed ? <ImageModal src={zoomed} onClose={() => setZoomed(null)} /> : null}
    </>
  );
}

function Draft({ label, hint }: { label: string; hint: "timeline" | "editor" }) {
  return (
    <div
      data-rfc-empty="drafting"
      className="flex flex-col items-start gap-1 rounded-md border border-shadow-purple/60 bg-void-900/40 p-4 text-sm text-soul-cyan/80"
    >
      <p className="font-medium text-ghost-white">{label}</p>
      <p className="text-xs text-soul-cyan/70">
        {hint === "timeline"
          ? "It will appear here when ready — watch live progress in the Agent activity timeline above."
          : "It will appear here when the agent finishes writing it."}
      </p>
    </div>
  );
}

function PendingClassifier() {
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

function NoRfc({
  issueKey,
  reason,
  onSummon,
}: {
  issueKey: string;
  reason: string | null;
  onSummon?: () => void;
}) {
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
