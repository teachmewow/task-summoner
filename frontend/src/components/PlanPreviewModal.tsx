import { useOpenPlan, usePlan } from "~/lib/plans";
import { MarkdownPreviewModal } from "./MarkdownPreviewModal";

/** Thin wrapper: bind the plan hook + editor launcher into the preview modal. */
interface Props {
  issueKey: string;
  open: boolean;
  onClose: () => void;
}

export function PlanPreviewModal({ issueKey, open, onClose }: Props) {
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
    />
  );
}
