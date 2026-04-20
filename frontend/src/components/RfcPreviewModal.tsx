import { useRfc } from "~/lib/rfcs";
import { MarkdownPreviewModal } from "./MarkdownPreviewModal";

/**
 * Thin wrapper: bind the RFC react-query hook into ``MarkdownPreviewModal``.
 *
 * Lazy-loads the RFC only when ``open`` flips true (``useRfc(null)`` when
 * closed) so gate cards that never open the modal don't pay the fetch cost.
 */
interface Props {
  issueKey: string;
  open: boolean;
  onClose: () => void;
}

export function RfcPreviewModal({ issueKey, open, onClose }: Props) {
  const query = useRfc(open ? issueKey : null);
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
    />
  );
}
