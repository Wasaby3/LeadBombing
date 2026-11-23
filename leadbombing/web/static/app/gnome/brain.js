/* The gnome's mind, without DOM or timers: reduce(state, event, random) → { state, effects }.
   Events: tick, activity (mouse/keys), status (a lead's status changed), client (a lead made a client), poke (a click),
   command (hide/show from a search field), action (something the user did, see actions.js). Effects: say, sleep, wake, angry, leave, enter. State is never mutated. */
import { PHRASES, milestonePhrases } from './phrases.js';
import { ACTIONS, actionPhrases } from './actions.js';

const MIN = 60 * 1000;
export const TIMING = Object.freeze({
  NAG_AFTER_MS: 10 * MIN,     // no lead work this long → «Чё не работаем?», then again after the same time
  STARE_AFTER_MS: 2 * MIN,    // no mouse or keys this long → «Чё завис, работничек?», once until the next activity
  SLEEP_AFTER_MS: 5 * MIN,    // no mouse or keys this long → the gnome falls asleep
  JAB_MIN_MS: 6 * MIN,        // a random jab comes between these two
  JAB_MAX_MS: 14 * MIN,
  ANGER_WINDOW_MS: 4000,      // a poke within this of the last one makes the gnome angrier
  ACTION_REPEAT_MS: 90 * 1000, // the same action is commented at most this often
  ACTION_GAP_MS: 6000,        // a low-key action is not commented this soon after any phrase
});
const LOW_KEY_CHANCE = 0.6;   // a low-key action (a page, a card, a copy…) is commented this often
const MAX_ANGER = PHRASES.angry.length;
const NOT_WRITTEN = 'not_written';
const MOODS = { praise: 'happy', milestone: 'happy', client: 'happy', refused: 'talk', nag: 'grumpy', jab: 'grumpy',
  angry: 'angry', woken: 'angry', wakeUp: 'talk', leaving: 'sad', back: 'happy', alreadyHere: 'grumpy', stare: 'grumpy' };

export const isMilestone = (n) => n === 1 || n === 5 || (n > 0 && n % 10 === 0);

const pad = (n) => String(n).padStart(2, '0');
export function dayOf(now) {
  const d = new Date(now);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

const nextJab = (now, random) => now + TIMING.JAB_MIN_MS + Math.floor(random() * (TIMING.JAB_MAX_MS - TIMING.JAB_MIN_MS));

/* Saved memory from an untrusted store: anything malformed is dropped; the count is today's only. */
function cleanMemory(memory, today) {
  const m = memory && typeof memory === 'object' ? memory : {};
  const sameDay = m.day === today;
  const count = sameDay && Number.isInteger(m.count) && m.count >= 0 ? m.count : 0;
  const counted = sameDay && Array.isArray(m.counted) ? m.counted.filter((k) => typeof k === 'string') : [];
  return { count, counted, hidden: m.hidden === true };
}

export function initialState(now, memory, random) {
  const day = dayOf(now);
  return {
    day, ...cleanMemory(memory, day),
    asleep: false, lastWorkAt: now, lastActivityAt: now, lastNagAt: now, nextJabAt: nextJab(now, random),
    anger: 0, lastPokeAt: -Infinity, lastSaid: {}, stared: false, lastSpokeAt: -Infinity, lastActionAt: {},
  };
}

/* What is kept between visits (localStorage, per login). */
export const memoryOf = ({ day, count, counted, hidden }) => ({ day, count, counted, hidden });

/* A phrase of the list other than the last one said for this category. */
function pick(list, last, random) {
  const options = list.length > 1 ? list.filter((p) => p !== last) : list;
  return options[Math.min(options.length - 1, Math.floor(random() * options.length))];
}

/* Say a phrase: returns the state with it remembered and the effect. */
function say(state, category, random, list = PHRASES[category]) {
  const key = category === 'angry' ? `angry${state.anger}` : category;
  const text = pick(list, state.lastSaid[key], random);
  return [{ ...state, lastSaid: { ...state.lastSaid, [key]: text } }, { type: 'say', category, text, mood: MOODS[category] }];
}

/* Chain several say() calls: [state, effects] → [state, effects + say]. */
function sayAll(state, categories, random) {
  return categories.reduce(([s, effects], [category, list]) => {
    const [next, effect] = say(s, category, random, list);
    return [next, [...effects, effect]];
  }, [state, []]);
}

function rollDay(state, now) {
  const day = dayOf(now);
  return day === state.day ? state : { ...state, day, count: 0, counted: [] };
}

/* A lead counts as processed once a day: the first time it leaves «Ещё не написал», or is made a client. */
function countLead(state, key, processed) {
  if (!processed || state.counted.includes(key)) return [state, false];
  return [{ ...state, count: state.count + 1, counted: [...state.counted, key] }, true];
}

const touch = (state, now) => ({ ...state, lastActivityAt: now, lastWorkAt: now, asleep: false, stared: false });

function onTick(state, now, random) {
  if (state.hidden) return { state, effects: [] };
  if (state.asleep) return { state, effects: [] };
  if (now - state.lastActivityAt >= TIMING.SLEEP_AFTER_MS) return { state: { ...state, asleep: true }, effects: [{ type: 'sleep' }] };
  if (!state.stared && now - state.lastActivityAt >= TIMING.STARE_AFTER_MS) {
    const [next, effect] = say({ ...state, stared: true }, 'stare', random);
    return { state: next, effects: [effect] };
  }
  if (now - state.lastWorkAt >= TIMING.NAG_AFTER_MS && now - state.lastNagAt >= TIMING.NAG_AFTER_MS) {
    const [next, effect] = say({ ...state, lastNagAt: now }, 'nag', random);
    return { state: next, effects: [effect] };
  }
  if (now >= state.nextJabAt) {
    const [next, effect] = say({ ...state, nextJabAt: nextJab(now, random) }, 'jab', random);
    return { state: next, effects: [effect] };
  }
  return { state, effects: [] };
}

function onActivity(state, now, random) {
  const awake = { ...state, lastActivityAt: now, asleep: false, stared: false };
  if (!state.asleep || state.hidden) return { state: awake, effects: [] };
  const [next, effect] = say(awake, 'wakeUp', random);
  return { state: next, effects: [{ type: 'wake' }, effect] };
}

function onStatus(state, { now, key, from, to }, random) {
  const [counted, isNew] = countLead(touch(state, now), key, from === NOT_WRITTEN && to !== NOT_WRITTEN);
  const wake = state.asleep ? [{ type: 'wake' }] : [];
  if (state.hidden) return { state: counted, effects: [] };
  const category = isNew && isMilestone(counted.count) ? 'milestone'
    : to === 'refused' ? 'refused' : to === NOT_WRITTEN ? null : 'praise';
  if (!category) return { state: counted, effects: wake };
  const list = category === 'milestone' ? milestonePhrases(counted.count) : PHRASES[category];
  const [next, said] = sayAll(counted, [[category, list]], random);
  return { state: next, effects: [...wake, ...said] };
}

function onClient(state, { now, key }, random) {
  const [counted, isNew] = countLead(touch(state, now), key, true);
  if (state.hidden) return { state: counted, effects: [] };
  const lines = [['client', PHRASES.client],
    ...(isNew && isMilestone(counted.count) ? [['milestone', milestonePhrases(counted.count)]] : [])];
  const [next, said] = sayAll(counted, lines, random);
  return { state: next, effects: [...(state.asleep ? [{ type: 'wake' }] : []), ...said] };
}

function onPoke(state, now, random) {
  if (state.hidden) return { state, effects: [] };
  const anger = now - state.lastPokeAt <= TIMING.ANGER_WINDOW_MS ? Math.min(state.anger + 1, MAX_ANGER) : 1;
  const angry = { ...state, anger, lastPokeAt: now, lastActivityAt: now, asleep: false };
  const category = state.asleep ? 'woken' : 'angry';
  const [next, effect] = say(angry, category, random, category === 'angry' ? PHRASES.angry[anger - 1] : undefined);
  return { state: next, effects: [...(state.asleep ? [{ type: 'wake' }] : []), { type: 'angry', level: anger }, effect] };
}

function onCommand(state, now, command, random) {
  if (command === 'hide') {
    if (state.hidden) return { state, effects: [] };
    const [next, effect] = say({ ...state, hidden: true, asleep: false }, 'leaving', random);
    return { state: next, effects: [...(state.asleep ? [{ type: 'wake' }] : []), effect, { type: 'leave' }] };
  }
  if (command !== 'show') return { state, effects: [] };
  if (!state.hidden) {
    const [next, effect] = say(state, 'alreadyHere', random);
    return { state: next, effects: [effect] };
  }
  const back = { ...touch(state, now), hidden: false, lastNagAt: now, nextJabAt: nextJab(now, random) };
  const [next, effect] = say(back, 'back', random);
  return { state: next, effects: [{ type: 'enter' }, effect] };
}

/* Is the action to be commented now? Not too often, and a low-key one only sometimes and not over another phrase. */
function worthSaying(state, rule, action, now, random) {
  if (now - (state.lastActionAt[action] ?? -Infinity) < TIMING.ACTION_REPEAT_MS) return false;
  if (rule.important) return true;
  return now - state.lastSpokeAt >= TIMING.ACTION_GAP_MS && random() < LOW_KEY_CHANCE;
}

function onAction(state, { now, action, ...detail }, random) {
  const rule = ACTIONS[action];
  const active = { ...state, lastActivityAt: now, asleep: false, stared: false,
    lastWorkAt: rule?.work ? now : state.lastWorkAt };
  const wake = state.asleep && !state.hidden ? [{ type: 'wake' }] : [];
  if (!rule || state.hidden || !worthSaying(state, rule, action, now, random)) return { state: active, effects: wake };
  const marked = { ...active, lastActionAt: { ...active.lastActionAt, [action]: now } };
  const text = pick(actionPhrases(action, detail), state.lastSaid[action], random);
  const next = { ...marked, lastSaid: { ...marked.lastSaid, [action]: text } };
  return { state: next, effects: [...wake, { type: 'say', category: 'action', action, text, mood: rule.mood }] };
}

function handle(s, event, random) {
  switch (event.type) {
    case 'tick': return onTick(s, event.now, random);
    case 'activity': return onActivity(s, event.now, random);
    case 'status': return onStatus(s, event, random);
    case 'client': return onClient(s, event, random);
    case 'poke': return onPoke(s, event.now, random);
    case 'command': return onCommand(s, event.now, event.command, random);
    case 'action': return onAction(s, event, random);
    default: return { state: s, effects: [] };
  }
}

/* After anything said, a random jab waits at least JAB_MIN_MS: the gnome does not chatter. */
export function reduce(state, event, random = Math.random) {
  const { state: next, effects } = handle(rollDay(state, event.now), event, random);
  if (!effects.some((e) => e.type === 'say')) return { state: next, effects };
  return { state: { ...next, lastSpokeAt: event.now, nextJabAt: Math.max(next.nextJabAt, event.now + TIMING.JAB_MIN_MS) }, effects };
}
