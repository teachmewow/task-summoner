import type { ToolItem } from "../types";
import type { ToolRenderer } from "./types";

const SHORT_ARGS_MAX = 80;

/**
 * Dedicated renderer for the ``Skill`` tool call.
 *
 * Product intent (ENG-132): the agent's top-level behaviour at each state is
 * "invoke a skill". Making the skill name visible without a click is the
 * difference between a readable timeline and a wall of generic boxes.
 *
 * Header layout:
 *   ``Skill: task-summoner-workflows:ticket-plan``
 *
 * When ``args`` fits on one line and under 80 chars, it appears inline after
 * an em-dash. Longer / multi-line args drop to the expandable body (same as
 * any other tool).
 */
export const renderSkill: ToolRenderer = (event) => {
  const skillName = extractSkillName(event.toolInput);
  const args = extractArgs(event.toolInput);
  const shortArgs = args && isShortSingleLine(args) ? args : null;

  return {
    defaultCollapsed: true,
    header: (
      <>
        <span className="font-semibold text-ghost-white" data-skill-name={skillName ?? ""}>
          Skill: {skillName ?? "(unknown)"}
        </span>
        {shortArgs ? <span className="truncate text-soul-cyan/70">— args: {shortArgs}</span> : null}
      </>
    ),
    body: <SkillBody event={event} />,
  };
};

function SkillBody({ event }: { event: ToolItem }) {
  return (
    <>
      <div className="mb-2">
        <p className="mb-1 text-[10px] uppercase tracking-wider text-arise-violet-bright/70">
          Input
        </p>
        <pre className="overflow-x-auto rounded border border-shadow-purple/40 bg-void-900/60 p-2 text-[11px] text-soul-cyan/90">
          {JSON.stringify(event.toolInput ?? {}, null, 2)}
        </pre>
      </div>
      <div>
        <p className="mb-1 text-[10px] uppercase tracking-wider text-arise-violet-bright/70">
          Result
        </p>
        {event.running ? (
          <p className="text-soul-cyan/60">Waiting for result…</p>
        ) : (
          <pre className="overflow-x-auto rounded border border-shadow-purple/40 bg-void-900/60 p-2 text-[11px] text-soul-cyan/90 whitespace-pre-wrap">
            {event.toolResult ?? "(no output)"}
          </pre>
        )}
      </div>
    </>
  );
}

function extractSkillName(input: Record<string, unknown> | null): string | null {
  if (!input) return null;
  const value = input.skill;
  if (typeof value === "string" && value.length > 0) return value;
  return null;
}

function extractArgs(input: Record<string, unknown> | null): string | null {
  if (!input) return null;
  const value = input.args;
  if (typeof value === "string" && value.length > 0) return value;
  return null;
}

function isShortSingleLine(value: string): boolean {
  if (value.includes("\n")) return false;
  return value.length <= SHORT_ARGS_MAX;
}
