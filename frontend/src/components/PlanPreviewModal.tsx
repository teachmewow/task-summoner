import { usePlan } from "~/lib/plans";
import { MarkdownPreviewModal } from "./MarkdownPreviewModal";

/** Thin wrapper: bind the plan hook into ``MarkdownPreviewModal``. */
interface Props {
  issueKey: string;
  open: boolean;
  onClose: () => void;
}

export function PlanPreviewModal({ issueKey, open, onClose }: Props) {
  const query = usePlan(open ? issueKey : null);
  return (
    <MarkdownPreviewModal
      issueKey={issueKey}
      label="Plan"
      open={open}
      onClose={onClose}
      data={query.data}
      isLoading={query.isLoading}
      isError={query.isError}
      error={query.error}
    />
  );
}
