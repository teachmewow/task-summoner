import { useCallback } from "react";
import { useTicket } from "~/lib/issues";
import { rfcImageUrl, useOpenRfc, useRfc } from "~/lib/rfcs";
import { MarkdownPreviewModal } from "./MarkdownPreviewModal";

/**
 * Thin wrapper: bind the RFC react-query hook + image rewriting into
 * ``MarkdownPreviewModal``.
 *
 * Lazy-loads the RFC only when ``open`` flips true (``useRfc(null)`` when
 * closed) so gate cards that never open the modal don't pay the fetch cost.
 * The PR URL shown in the header comes from ``TicketContext.metadata.rfc_pr_url``
 * — sourced directly from the orchestrator store so the link stays
 * available on terminal states (DONE / FAILED) where the gate response no
 * longer surfaces the URL.
 */
interface Props {
  issueKey: string;
  open: boolean;
  onClose: () => void;
}

export function RfcPreviewModal({ issueKey, open, onClose }: Props) {
  const query = useRfc(open ? issueKey : null);
  const ticket = useTicket(open ? issueKey : null);
  const openEditor = useOpenRfc(issueKey);
  const prUrl = (ticket.data?.metadata?.rfc_pr_url as string | undefined) ?? null;

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
      prUrl={prUrl}
    />
  );
}
