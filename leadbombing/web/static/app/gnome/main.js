/* The gnome in the bottom right corner of every page: wires the brain (brain.js) to the page, the 3D scene and the bubble.
   It listens to the app: lb:user (login/logout, from app.js), lb:lead-status and lb:lead-client (from crm.js),
   lb:action (what the user does: a sphere, a search, a page… see actions.js),
   the secret phrases in any search field, and the user's activity. It remembers per login what brain.memoryOf says. */
import { initialState, reduce, memoryOf } from './brain.js';
import { parseCommand } from './commands.js';
import { createBubble } from './bubble.js';

const TICK_MS = 15 * 1000;
const ACTIVITY_THROTTLE_MS = 1000;
const LEAVE_AFTER_MS = 1600;        // the farewell phrase is read before the gnome walks away
const MEMORY_PREFIX = 'lb.gnome.';
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)');

const box = document.getElementById('gnome');
const canvas = box.querySelector('canvas');
const hit = box.querySelector('.gnome-hit');
const bubble = createBubble(box.querySelector('.gnome-bubble'));

let login = null;
let state = null;
let scene = null;
let scenePromise = null;
let tickTimer = 0;
let lastActivity = 0;
let shownGen = 0;        // bumped on every show: a leave started before it must not hide the gnome again

const memoryKey = () => MEMORY_PREFIX + login;
function loadMemory() {
  try { return JSON.parse(localStorage.getItem(memoryKey())) ?? {}; } catch { return {}; }
}
function saveMemory() {
  try { localStorage.setItem(memoryKey(), JSON.stringify(memoryOf(state))); } catch { /* private mode: forgets on reload */ }
}

/* The bubble over the head and the click area over the body follow the gnome as it walks. */
function place({ x, y, halfWidth }) {
  bubble.place({ x, y });
  hit.style.left = (x - halfWidth) + 'px';
  hit.style.width = (halfWidth * 2) + 'px';
  hit.style.top = y + 'px';
}

/* The 3D scene is loaded the first time the gnome is shown; without WebGL a flat picture stands in. */
function ensureScene() {
  scenePromise ??= import('./scene.js')
    .then(({ createGnomeScene }) => {
      scene = createGnomeScene(canvas, { reducedMotion: REDUCED.matches, onFrame: place });
      return scene;
    })
    .catch((e) => {
      console.warn('[gnome] 3D is off, a picture stands in:', e);
      box.classList.add('flat');
      return null;
    });
  return scenePromise;
}

async function show({ walkIn }) {
  shownGen += 1;
  box.hidden = false;
  const s = await ensureScene();
  s?.resume();
  if (walkIn) await s?.enter();
}

/* Gone while the gnome is still to be hidden: «гном вернись» or a logout since then cancels the rest. */
const stillLeaving = (gen) => gen === shownGen && state?.hidden;

async function leave() {
  const gen = shownGen;
  await new Promise((resolve) => setTimeout(resolve, LEAVE_AFTER_MS));
  if (!stillLeaving(gen)) return;
  await scene?.leave();
  if (!stillLeaving(gen)) return;
  box.hidden = true;
  bubble.clear();
  scene?.pause();
}

function apply(effect) {
  switch (effect.type) {
    case 'say':
      if (effect.mood === 'angry') bubble.interrupt(effect.text, effect.mood);
      else bubble.say(effect.text, effect.mood);
      scene?.mood(effect.mood);
      break;
    case 'sleep': scene?.sleep(); bubble.sleep(true); break;
    case 'wake': scene?.wake(); bubble.sleep(false); break;
    case 'angry': scene?.angry(effect.level); break;
    case 'leave': leave(); break;
    case 'enter': show({ walkIn: true }); break;
    default: break;
  }
}

function dispatch(event) {
  if (!state) return;
  const before = JSON.stringify(memoryOf(state));
  const { state: next, effects } = reduce(state, { now: Date.now(), ...event });
  state = next;
  if (JSON.stringify(memoryOf(state)) !== before) saveMemory();
  effects.forEach(apply);
}

function start(user) {
  bubble.clear();
  scene?.wake();
  login = user;
  state = initialState(Date.now(), loadMemory(), Math.random);
  if (!state.hidden) show({ walkIn: true });
  clearInterval(tickTimer);
  tickTimer = setInterval(() => dispatch({ type: 'tick' }), TICK_MS);
}

function stop() {
  clearInterval(tickTimer);
  shownGen += 1;
  state = null;
  login = null;
  box.hidden = true;
  bubble.clear();
  scene?.pause();
}

function onUser(user) {
  if (user === login) return;
  if (user) start(user); else stop();
}

function onActivity() {
  const now = Date.now();
  if (now - lastActivity < ACTIVITY_THROTTLE_MS) return;
  lastActivity = now;
  dispatch({ type: 'activity' });
}

/* «гном съеби» / «гном вернись» in any search field: the field is cleared, so no search runs on the phrase. */
function onSearchInput(e) {
  const field = e.target;
  if (!(field instanceof HTMLInputElement) || field.type !== 'search') return;
  const command = parseCommand(field.value);
  if (!command) return;
  field.value = '';
  field.dispatchEvent(new Event('input', { bubbles: true }));
  dispatch({ type: 'command', command });
}

const onPoke = () => dispatch({ type: 'poke' });

window.addEventListener('lb:user', (e) => onUser(e.detail?.login || null));
window.addEventListener('lb:lead-status', (e) => dispatch({ type: 'status', ...e.detail }));
window.addEventListener('lb:lead-client', (e) => dispatch({ type: 'client', ...e.detail }));
window.addEventListener('lb:action', (e) => e.detail?.action && dispatch({ ...e.detail, type: 'action' }));
document.addEventListener('input', onSearchInput, true);
for (const type of ['pointermove', 'pointerdown', 'keydown', 'wheel', 'touchstart']) {
  window.addEventListener(type, onActivity, { passive: true });
}
document.addEventListener('visibilitychange', () => document.visibilityState === 'visible' && dispatch({ type: 'tick' }));
hit.addEventListener('click', onPoke);
box.querySelector('.gnome-flat').addEventListener('click', onPoke);
if (window.lbUser) onUser(window.lbUser);
