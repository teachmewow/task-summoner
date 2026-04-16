/**
 * API layer — SSE connection and REST API calls.
 * Handles data fetching and pushes updates into the shared state.
 */
import { state } from './state.js';
import { renderTickets, selectTicket, updateStats } from './tickets.js';
import { appendNewEvents } from './event-log.js';

const EVENT_TYPES = [
  'ticket_discovered', 'state_transition', 'agent_started', 'agent_message',
  'agent_tool_use', 'agent_completed', 'ticket_error', 'approval_waiting',
  'approval_received',
];

let evtSource = null;

export function connectSSE() {
  if (evtSource) { try { evtSource.close(); } catch (_) {} }

  evtSource = new EventSource('/api/events/stream');
  evtSource.onopen = () => setConn(true);
  evtSource.onerror = () => {
    setConn(false);
    setTimeout(connectSSE, 3000);
  };

  EVENT_TYPES.forEach(type =>
    evtSource.addEventListener(type, e => handleEvent(JSON.parse(e.data)))
  );
}

export async function loadInitial() {
  try {
    const [tRes, eRes] = await Promise.all([
      fetch('/api/tickets'),
      fetch('/api/events/history'),
    ]);
    const tickets = await tRes.json();
    const events = await eRes.json();

    tickets.forEach(ctx => {
      ensureTicket(ctx.ticket_key);
      state.tickets[ctx.ticket_key].context = ctx;
    });
    events.forEach(e => {
      ensureTicket(e.ticket_key);
      state.tickets[e.ticket_key].events.push(e);
    });

    renderTickets();
    updateStats();

    const keys = Object.keys(state.tickets);
    if (keys.length && !state.selectedTicket) selectTicket(keys[0]);
  } catch (e) {
    console.error('Load failed:', e);
  }
}

function handleEvent(event) {
  const key = event.ticket_key;
  ensureTicket(key);
  const t = state.tickets[key];
  t.events.push(event);

  if (event.event_type === 'state_transition') {
    t.context.state = event.new_state;
  }
  if (event.event_type === 'ticket_discovered') {
    t.context.state = 'QUEUED';
    t.context.summary = event.summary;
    t.context.ticket_key = key;
  }
  if (event.event_type === 'agent_completed') {
    t.context.total_cost_usd = (t.context.total_cost_usd || 0) + (event.cost_usd || 0);
  }

  renderTickets();
  if (state.selectedTicket === key) appendNewEvents();
  updateStats();
}

function ensureTicket(key) {
  if (!state.tickets[key]) {
    state.tickets[key] = { context: {}, events: [] };
  }
}

function setConn(ok) {
  document.getElementById('connDot').className =
    'conn-dot ' + (ok ? 'connected' : 'disconnected');
  document.getElementById('connText').textContent =
    ok ? 'live' : 'reconnecting';
}
