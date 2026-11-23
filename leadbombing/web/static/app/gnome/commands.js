/* Secret phrases typed into any search field: «гном съеби» hides the gnome, «гном вернись» brings it back.
   Case, «ё», punctuation and extra spaces do not matter; anything else is an ordinary search. */
const COMMANDS = { 'гном съеби': 'hide', 'гном вернись': 'show' };

export function normalize(text) {
  return String(text ?? '').toLowerCase().replace(/ё/g, 'е').replace(/[^\p{L}\p{N}\s]/gu, ' ').replace(/\s+/g, ' ').trim();
}

/* 'hide' | 'show' | null */
export function parseCommand(text) {
  return COMMANDS[normalize(text)] ?? null;
}
