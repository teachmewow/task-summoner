import type { ReactNode } from "react";
import type { ToolItem } from "../types";

/**
 * Strategy-pattern contract for rendering a single tool call row.
 *
 * Per ENG-132: each known ``tool_name`` registers a renderer that shapes the
 * header (what's visible collapsed) and the body (what the expanded panel
 * shows). ``defaultCollapsed`` lets a renderer decide whether expansion is
 * required for a useful glance — errored rows still get overridden by the
 * timeline (auto-expand on error) regardless of this hint.
 */
export interface ToolRenderOutput {
  header: ReactNode;
  body: ReactNode;
  defaultCollapsed: boolean;
}

export type ToolRenderer = (event: ToolItem) => ToolRenderOutput;
