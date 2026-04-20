import { useCallback } from "react";
import { rfcImageUrl, useOpenRfc, useRfc } from "~/lib/rfcs";
import { MarkdownPreviewModal } from "./MarkdownPreviewModal";

/**
 * Thin wrapper: bind the RFC react-query hook + image rewriting into
 * ``MarkdownPreviewModal``.
 *
 * Lazy-loads the RFC only when ``open`` flips true (``useRfc(null)`` when
 * closed) so gate cards that never open the modal don't pay the fetch cost.
 * The ``postRender`` callback rewrites relative image paths to the API image
 * endpoint so images embedded in the RFC render correctly inside the modal.
 */
interface Props {
  issueKey: string;
  open: boolean;
  onClose: () => void;
  /** PR URL this artifact belongs to, shown as a "View PR" link in the modal header. */
  prUrl?: string | null;
}

export function RfcPreviewModal({ issueKey, open, onClose, prUrl }: Props) {
  const query = useRfc(open ? issueKey : null);
  const openEditor = useOpenRfc(issueKey);

  const postRender = useCallback(
    (container: HTMLElement) => {
      const imgs = container.querySelectorAll("img");
      for (const img of Array.from(imgs)) {
        const src = img.getAttribute("src") ?? "";
        if (/^https?:/i.test(src) || src.startsWith("/")) continue;
        img.setAttribute("src", rfcImageUrl(issueKey, src));
        img.setAttribute("loading", "lazy");
      }
    },
    [issueKey],
  );

  return (
    <MarkdownPreviewModal
      issueKey={issueKey}
      label="RFC"
      open={open}
      onClose={onClose}
      data={query.data}
      isLoading={query.isLoading}
      isError={query.isError}
      error={query.error}
      openEditor={{
        mutate: () => openEditor.mutate(undefined),
        isPending: openEditor.isPending,
      }}
      postRender={postRender}
      prUrl={prUrl ?? null}
    />
  );
}
