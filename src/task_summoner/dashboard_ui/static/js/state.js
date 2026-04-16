/**
 * Application state — single source of truth.
 *
 * tickets: { [key]: { context: {...}, events: [...] } }
 * selectedTicket: currently selected ticket key (or null)
 * activeFilter: 'all' | event_type string
 * renderedCount: how many filtered events have been rendered for the current ticket
 */
export const state = {
  tickets: {},
  selectedTicket: null,
  activeFilter: 'all',
  renderedCount: 0,
};

export const TERMINAL_STATES = new Set(['DONE', 'FAILED']);
