/**
 * Event log panel — renders the right-side event stream.
 *
 * Both renderLog() (full re-render) and appendNewEvents() (incremental)
 * use the same appendSmart() function, so grouping behavior is identical
 * regardless of whether events come from history or SSE.
 */
import { state } from './state.js';
import { fmtState } from './utils.js';
import { createEntryElement } from './event-renderer.js';
import { tryMergeToolEvent } from './tool-grouper.js';

/** Full re-render — used on ticket switch or filter change. */
export function renderLog() {
  state.renderedCount = 0;
  const container = document.getElementById('logEntries');
  container.innerHTML = '';

  const data = state.tickets[state.selectedTicket];
  if (!data) {
    container.innerHTML =
      '<div class="empty-state">' +
        '<div class="empty-state-icon">&#9678;</div>' +
        '<div class="empty-state-text">No events yet</div>' +
      '</div>';
    return;
  }

  updateToolbar(data.context);
  const events = getFilteredEvents(data);

  for (const event of events) {
    appendSmart(container, event);
  }

  state.renderedCount = events.length;
  scrollToBottom(container);
}

/** Incremental append — used when SSE delivers new events. No flicker. */
export function appendNewEvents() {
  const container = document.getElementById('logEntries');
  const data = state.tickets[state.selectedTicket];
  if (!data) return;

  updateToolbar(data.context);

  const events = getFilteredEvents(data);
  const newEvents = events.slice(state.renderedCount);
  if (!newEvents.length) return;

  // Only auto-scroll if user is already near the bottom (not inspecting old events)
  const wasAtBottom = isNearBottom(container);

  for (const event of newEvents) {
    appendSmart(container, event);
  }

  state.renderedCount = events.length;
  if (wasAtBottom) scrollToBottom(container);
}

/**
 * Append a single event to the container, using tool grouping for tool_use events.
 * This is the shared logic between renderLog and appendNewEvents.
 */
function appendSmart(container, event) {
  if (event.event_type === 'agent_tool_use') {
    if (!tryMergeToolEvent(container, event)) {
      container.appendChild(createEntryElement(event));
    }
  } else {
    container.appendChild(createEntryElement(event));
  }
}

function getFilteredEvents(data) {
  return state.activeFilter === 'all'
    ? data.events
    : data.events.filter(e => e.event_type === state.activeFilter);
}

function updateToolbar(ctx) {
  const badge = document.getElementById('logState');
  if (ctx?.state) {
    badge.style.display = '';
    badge.className = 'state-badge state-' + ctx.state;
    badge.textContent = fmtState(ctx.state);
  } else {
    badge.style.display = 'none';
  }
}

function isNearBottom(el) {
  return el.scrollHeight - el.scrollTop - el.clientHeight < 100;
}

function scrollToBottom(el) {
  el.scrollTop = el.scrollHeight;
}
