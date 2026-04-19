import type { ToolItem } from "../types";
import { renderSkill } from "./Skill";
import { renderDefault } from "./default";
import type { ToolRenderer } from "./types";

/**
 * Registry of per-tool renderers.
 *
 * Adding a new renderer = add one entry here + one file under this directory.
 * The timeline's core component never learns the list — it just calls
 * ``renderTool`` and composes whatever the registered renderer returns.
 */
export const TOOL_RENDERERS: Record<string, ToolRenderer> = {
  Skill: renderSkill,
};

export function renderTool(event: ToolItem) {
  return (TOOL_RENDERERS[event.toolName] ?? renderDefault)(event);
}

export { renderDefault, renderSkill };
export type { ToolRenderer } from "./types";
