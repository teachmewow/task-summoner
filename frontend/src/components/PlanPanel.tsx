import { useOpenPlan, usePlan } from "~/lib/plans";
import { MarkdownArtifactPanel } from "./MarkdownArtifactPanel";

/**
 * Thin wrapper around ``MarkdownArtifactPanel`` for the implementation plan.
 *
 * Plans don't have image sidecars, so we pass no ``postRender``. Empty-state
 * copy is context-aware — during planning states the panel tells the user
 * the agent is drafting; for unrelated states (QUEUED / doc review / done /
 * failed) the panel just says "no plan yet".
 */
interface Props {
  issueKey: string;
  orchestratorState?: string | null;
}

const PLAN_DRAFTING_STATES = new Set(["PLANNING"]);
const PLAN_VISIBLE_STATES = new Set([
  "WAITING_PLAN_REVIEW",
  "IMPLEMENTING",
  "WAITING_MR_REVIEW",
  "FIXING_MR",
  "DONE",
]);

export function PlanPanel({ issueKey, orchestratorState }: Props) {
  const query = usePlan(issueKey);
  const openMutation = useOpenPlan(issueKey);

  const emptyState =
    orchestratorState && PLAN_DRAFTING_STATES.has(orchestratorState) ? (
      <DraftingPlan />
    ) : orchestratorState && PLAN_VISIBLE_STATES.has(orchestratorState) ? (
      <PlanLostOrPending issueKey={issueKey} />
    ) : (
      <NoPlanYet issueKey={issueKey} />
    );

  return (
    <MarkdownArtifactPanel
      label="Plan"
      kind="plan"
      data={query.data}
      isLoading={query.isLoading}
      isError={query.isError}
      error={query.error}
      openEditor={{
        mutate: () => openMutation.mutate(undefined),
        isPending: openMutation.isPending,
      }}
      emptyState={emptyState}
    />
  );
}

function DraftingPlan() {
  return (
    <div
      data-plan-empty="drafting"
      className="flex flex-col items-start gap-1 rounded-md border border-shadow-purple/60 bg-void-900/40 p-4 text-sm text-soul-cyan/80"
    >
      <p className="font-medium text-ghost-white">Agent is drafting the plan.</p>
      <p className="text-xs text-soul-cyan/70">
        It will appear here when ready — watch live progress in the Agent activity timeline above.
      </p>
    </div>
  );
}

function PlanLostOrPending({ issueKey }: { issueKey: string }) {
  return (
    <div
      data-plan-empty="missing"
      className="flex flex-col items-start gap-1 rounded-md border border-shadow-purple/60 bg-void-900/40 p-4 text-sm text-soul-cyan/80"
    >
      <p>
        No <code className="text-ghost-white/90">plan.md</code> on disk for{" "}
        <code className="text-ghost-white/90">{issueKey}</code> yet.
      </p>
      <p className="text-xs text-soul-cyan/70">
        The orchestrator stores it at <code>artifacts/{issueKey}/plan.md</code>. If you expected one
        here, check the timeline for a failed planning run.
      </p>
    </div>
  );
}

function NoPlanYet({ issueKey }: { issueKey: string }) {
  return (
    <div
      data-plan-empty="generic"
      className="flex flex-col items-start gap-1 rounded-md border border-shadow-purple/60 bg-void-900/40 p-4 text-sm text-soul-cyan/80"
    >
      <p>
        No plan yet for <code className="text-ghost-white/90">{issueKey}</code>.
      </p>
      <p className="text-xs text-soul-cyan/70">
        The plan is drafted after the doc gate is approved (or right away for tickets without the{" "}
        <code>Doc</code> label).
      </p>
    </div>
  );
}
