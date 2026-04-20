import { useOpenPlan, usePlan } from "~/lib/plans";
import { MarkdownPreviewModal } from "./MarkdownPreviewModal";

/** Thin wrapper: bind the plan hook + editor launcher into the preview modal. */
interface Props {
  issueKey: string;
  open: boolean;
  onClose: () => void;
  /** PR URL this artifact belongs to, shown as a "View PR" link in the modal header. */
  prUrl?: string | null;
}

export function PlanPreviewModal({ issueKey, open, onClose, prUrl }: Props) {
  const query = usePlan(open ? issueKey : null);
  const openEditor = useOpenPlan(issueKey);
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
      openEditor={{
        mutate: () => openEditor.mutate(undefined),
        isPending: openEditor.isPending,
      }}
      prUrl={prUrl ?? null}
    />
  );
}
