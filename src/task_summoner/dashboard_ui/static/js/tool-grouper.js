/**
 * Tool call grouping — merges consecutive agent_tool_use events into
 * collapsible groups in the DOM.
 *
 * This module handles the tricky part: SSE delivers events one at a time,
 * so we need to detect when a new tool event is adjacent to an existing
 * tool entry and dynamically upgrade/extend groups.
 *
 * Three cases when a tool_use event arrives:
 *   1. Previous sibling is a .tool-group  → extend it
 *   2. Previous sibling is a .log-entry.agent_tool_use → upgrade both to a group
 *   3. Neither → render individually (may become a group when next tool arrives)
 */
import { createEntryElement } from './event-renderer.js';

/**
 * Try to merge a tool_use event with the previous DOM element.
 * @returns {boolean} true if merged, false if caller should render individually.
 */
export function tryMergeToolEvent(container, event) {
  const lastChild = container.lastElementChild;
  if (!lastChild) return false;

  // Case 1: extend existing tool group
  if (lastChild.classList.contains('tool-group')) {
    extendGroup(lastChild, event);
    return true;
  }

  // Case 2: upgrade individual tool entry + new event into a group
  if (lastChild.classList.contains('agent_tool_use')) {
    upgradeToGroup(container, lastChild, event);
    return true;
  }

  return false;
}

/** Add one more entry to an existing tool group and refresh its header. */
function extendGroup(group, event) {
  const body = group.querySelector('.tool-group-body');
  body.appendChild(createEntryElement(event));
  refreshGroupHeader(group);
}

/** Replace an individual tool entry with a 2-item group containing both events. */
function upgradeToGroup(container, existingEntry, newEvent) {
  const group = createGroupShell();
  const body = group.querySelector('.tool-group-body');

  // Move the existing individual entry into the group body
  container.removeChild(existingEntry);
  body.appendChild(existingEntry);
  body.appendChild(createEntryElement(newEvent));

  container.appendChild(group);
  refreshGroupHeader(group);
}

/** Create an empty tool-group shell (header + empty body). */
function createGroupShell() {
  const group = document.createElement('div');
  group.className = 'tool-group';
  group.innerHTML =
    `<div class="tool-group-header">` +
      `<span class="badge">TOOLS</span>` +
      `<span class="tool-count"></span>` +
      `<span class="tool-names"></span>` +
      `<span class="chevron">&#9656;</span>` +
    `</div>` +
    `<div class="tool-group-body"></div>`;

  group.querySelector('.tool-group-header').addEventListener('click', () => {
    group.classList.toggle('expanded');
  });

  return group;
}

/** Read tool names from group body entries and update the header text. */
function refreshGroupHeader(group) {
  const entries = group.querySelectorAll('.tool-group-body .log-entry');
  const names = new Set();
  entries.forEach(entry => {
    const strong = entry.querySelector('.log-content strong');
    if (strong) names.add(strong.textContent);
  });

  group.querySelector('.tool-count').textContent = `${entries.length} calls`;
  group.querySelector('.tool-names').textContent = [...names].join(', ');
}
