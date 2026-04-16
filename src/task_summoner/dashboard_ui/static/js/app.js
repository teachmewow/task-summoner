/**
 * Application entry point — wires modules together and boots the dashboard.
 */
import { state } from './state.js';
import { connectSSE, loadInitial } from './api.js';
import { renderLog } from './event-log.js';

function initFilters() {
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.activeFilter = btn.dataset.filter;
      renderLog();
    });
  });
}

function init() {
  initFilters();
  loadInitial().then(connectSSE);
}

init();
