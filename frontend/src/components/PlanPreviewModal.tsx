import { useTicket } from "~/lib/issues";
import { useOpenPlan, usePlan } from "~/lib/plans";
import { MarkdownPreviewModal } from "./MarkdownPreviewModal";

/**
 * Thin wrapper: bind the plan hook + editor launcher into the preview modal.
 *
 * PR URL in the header comes from ``TicketContext`` — prefers
 * ``metadata.plan_pr_url`` (set by ``PlanningState`` when the draft PR is
 * opened) and falls back to ``mr_url`` for the code-review gate where the
 * draft was flipped to ready and kept its number.
 */
interface Props {
  issueKey: string;
  open: boolean;
  onClose: () => void;
}

export function PlanPreviewModal({ issueKey, open, onClose }: Props) {
  const query = usePlan(open ? issueKey : null);
  const ticket = useTicket(open ? issueKey : null);
  const openEditor = useOpenPlan(issueKey);
  const prUrl =
    (ticket.data?.metadata?.plan_pr_url as string | undefined) ?? ticket.data?.mr_url ?? null;
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
      prUrl={prUrl}
    />
  );
}
