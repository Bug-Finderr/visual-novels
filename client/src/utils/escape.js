const ENTITY_MAP = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
};

export function escapeHtml(input) {
  if (input == null) return '';
  return String(input).replace(/[&<>"']/g, (ch) => ENTITY_MAP[ch]);
}
