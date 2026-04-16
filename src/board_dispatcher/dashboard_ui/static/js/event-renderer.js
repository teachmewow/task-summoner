/**
 * Event rendering — creates DOM elements for each event type.
 * Pure functions: input event → output DOM element. No side effects.
 */
import { esc, fmtState, fmtTime } from './utils.js';

/** Create a fully styled log-entry element for any event. */
export function createEntryElement(event) {
  const el = document.createElement('div');
  const extra = (event.event_type === 'agent_completed' && !event.success) ? ' failed' : '';
  el.className = 'log-entry ' + event.event_type + extra;
  el.innerHTML = `<span class="time">${fmtTime(event.timestamp)}</span>${renderContent(event)}`;
  return el;
}

function renderContent(e) {
  switch (e.event_type) {
    case 'ticket_discovered':
      return badge('IN PROGRESS') + `<span class="log-content"><strong>${e.ticket_key}</strong>: ${esc(e.summary || '')}</span>`;

    case 'state_transition':
      return badge('STATE') +
        `<span class="state-flow">` +
          `<span class="from">${fmtState(e.old_state)}</span>` +
          `<span class="arrow">&rarr;</span>` +
          `<span class="to">${fmtState(e.new_state)}</span>` +
          `<span class="trigger">${e.trigger}</span>` +
        `</span>`;

    case 'agent_started':
      return badge('START') +
        `<span class="log-content"><strong>${e.agent_name}</strong> &middot; ${e.model} &middot; ${e.max_turns} turns &middot; $${e.budget_usd}</span>`;

    case 'agent_message': {
      const txt = e.text.length > 400 ? e.text.slice(0, 400) + '...' : e.text;
      return badge('CLAUDIO') + `<span class="msg-text">${esc(txt)}</span>`;
    }

    case 'agent_tool_use': {
      const inp = e.tool_input ? JSON.stringify(e.tool_input).slice(0, 200) : '';
      return badge('TOOL') +
        `<span class="log-content"><strong>${e.tool_name}</strong></span>` +
        (inp ? `<span class="tool-detail">${esc(inp)}</span>` : '');
    }

    case 'agent_completed': {
      const ok = e.success;
      const sym = ok ? '&#10003;' : '&#10007;';
      const err = e.error ? ` &mdash; <em>${esc(e.error)}</em>` : '';
      return badge(ok ? 'DONE' : 'FAIL') +
        `<span class="log-content"><strong>${e.agent_name}</strong> ${sym} ${e.num_turns} turns &middot; $${(e.cost_usd || 0).toFixed(2)}${err}</span>`;
    }

    case 'ticket_error':
      return badge('ERR') + `<span class="log-content">${esc(e.error)}</span>`;

    case 'approval_waiting':
      return badge('WAIT') + `<span class="log-content">Waiting for human approval</span>`;

    case 'approval_received':
      return badge('OK') + `<span class="log-content">${e.decision} via ${e.source}</span>`;

    default:
      return badge(e.event_type.slice(0, 6).toUpperCase()) +
        `<span class="log-content">${esc(JSON.stringify(e).slice(0, 200))}</span>`;
  }
}

function badge(text) {
  return `<span class="badge">${text}</span>`;
}
