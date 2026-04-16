/**
 * Ticket list panel — left sidebar rendering and selection.
 */
import { state, TERMINAL_STATES } from './state.js';
import { esc, fmtState } from './utils.js';
import { renderLog } from './event-log.js';

export function renderTickets() {
  const panel = document.getElementById('ticketsPanel');
  panel.innerHTML = '';
  const entries = Object.entries(state.tickets);

  if (!entries.length) {
    panel.innerHTML =
      '<div class="empty-state" style="padding:40px 16px">' +
        '<div class="empty-state-text">No tickets yet' +
          '<span>Add label "claudio" to a Jira ticket</span>' +
        '</div>' +
      '</div>';
    return;
  }

  entries.forEach(([key, data]) => {
    const ctx = data.context || {};
    const st = ctx.state || 'QUEUED';
    const cost = (ctx.total_cost_usd || 0).toFixed(2);
    const card = document.createElement('div');
    card.className = 'ticket-card' + (state.selectedTicket === key ? ' active' : '');
    card.onclick = () => selectTicket(key);
    card.innerHTML =
      `<div class="ticket-key">${key}</div>` +
      `<div class="ticket-summary">${esc(ctx.summary || key)}</div>` +
      `<div class="ticket-meta">` +
        `<span class="state-badge state-${st}">${fmtState(st)}</span>` +
        `<span class="ticket-cost">$${cost}</span>` +
      `</div>`;
    panel.appendChild(card);
  });
}

export function selectTicket(key) {
  state.selectedTicket = key;
  document.getElementById('logTitle').textContent = key;
  renderTickets();
  renderLog();
}

export function updateStats() {
  const entries = Object.values(state.tickets);
  document.getElementById('statTickets').textContent = entries.length;
  document.getElementById('statActive').textContent =
    entries.filter(t => t.context?.state && !TERMINAL_STATES.has(t.context.state)).length;
  const cost = entries.reduce((s, t) => s + (t.context?.total_cost_usd || 0), 0);
  document.getElementById('statCost').textContent = '$' + cost.toFixed(2);
}
