/** Escape HTML to prevent XSS. */
export function esc(text) {
  const d = document.createElement('div');
  d.textContent = text;
  return d.innerHTML;
}

/** Format state enum for display (underscores → spaces; CSS handles casing). */
export function fmtState(s) {
  return (s || '').replace(/_/g, ' ');
}

/** Format ISO timestamp to HH:MM:SS. */
export function fmtTime(ts) {
  return new Date(ts).toLocaleTimeString('en-US', { hour12: false });
}
