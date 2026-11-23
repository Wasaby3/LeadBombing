import { test } from 'node:test';
import assert from 'node:assert/strict';
import { initialState, reduce, isMilestone, memoryOf, TIMING } from '../../leadbombing/web/static/app/gnome/brain.js';

const T0 = new Date(2026, 10, 23, 10, 0, 0).getTime();
const MIN = 60 * 1000;
const rnd = () => 0.5;
const start = (memory = {}) => initialState(T0, memory, rnd);
const says = (effects) => effects.filter((e) => e.type === 'say');
/* Lead i is processed: it leaves «Ещё не написал». */
const work = (state, i, now = T0) => reduce(state, { type: 'status', now, key: 'f/' + i, from: 'not_written', to: 'written' }, rnd);

test('milestones are the 1st, 5th and every 10th lead', () => {
  assert.deepEqual([1, 2, 4, 5, 6, 9, 10, 11, 20, 30, 35].map(isMilestone),
    [true, false, false, true, false, false, true, false, true, true, false]);
});

test('a processed lead is counted once', () => {
  const { state, effects } = work(start(), 1);
  assert.equal(state.count, 1);
  assert.equal(says(effects).length, 1);
  assert.equal(says(effects)[0].category, 'milestone');
  const again = reduce(state, { type: 'status', now: T0, key: 'f/1', from: 'written', to: 'in_progress' }, rnd);
  assert.equal(again.state.count, 1, 'the same lead is not counted twice');
  assert.equal(says(again.effects)[0].category, 'praise');
});

test('only the 1st, 5th and 10th of ten processed leads get milestone praise', () => {
  let state = start();
  const milestones = [];
  for (let i = 1; i <= 10; i += 1) {
    const r = work(state, i);
    state = r.state;
    const said = says(r.effects);
    assert.equal(said.length, 1);
    if (said[0].category === 'milestone') milestones.push(i);
    else assert.equal(said[0].category, 'praise');
  }
  assert.deepEqual(milestones, [1, 5, 10]);
});

test('a milestone text names the number of leads', () => {
  const state = start({ day: '2026-11-23', count: 9, counted: [] });
  assert.match(says(work(state, 10).effects)[0].text, /10/);
});

test('a lead made a client gets the bonus phrase and is counted if it was not', () => {
  const { state, effects } = reduce(start(), { type: 'client', now: T0, key: 'f/7' }, rnd);
  assert.equal(state.count, 1);
  assert.equal(says(effects)[0].category, 'client');
  assert.equal(says(effects)[1].category, 'milestone', 'the first lead is still a milestone');
});

test('a refusal gets a consoling phrase, a status back to «Ещё не написал» is ignored', () => {
  const refused = reduce(start(), { type: 'status', now: T0, key: 'f/1', from: 'written', to: 'refused' }, rnd);
  assert.equal(says(refused.effects)[0].category, 'refused');
  const back = reduce(start(), { type: 'status', now: T0, key: 'f/1', from: 'written', to: 'not_written' }, rnd);
  assert.equal(says(back.effects).length, 0);
});

test('no lead work for the nag time makes the gnome nag, and not again right away', () => {
  let state = start();
  state = reduce(state, { type: 'activity', now: T0 + TIMING.NAG_AFTER_MS - MIN }, rnd).state;
  const nag = reduce(state, { type: 'tick', now: T0 + TIMING.NAG_AFTER_MS }, rnd);
  assert.equal(says(nag.effects)[0].category, 'nag');
  const soon = reduce(nag.state, { type: 'tick', now: T0 + TIMING.NAG_AFTER_MS + MIN }, rnd);
  assert.equal(says(soon.effects).length, 0);
});

test('lead work resets the nag timer', () => {
  let state = work(start(), 1, T0 + 8 * MIN).state;
  state = reduce(state, { type: 'activity', now: T0 + 12 * MIN }, rnd).state;
  assert.equal(says(reduce(state, { type: 'tick', now: T0 + 12 * MIN }, rnd).effects).length, 0);
});

test('no activity for the sleep time puts the gnome to sleep, activity wakes it', () => {
  const asleep = reduce(start(), { type: 'tick', now: T0 + TIMING.SLEEP_AFTER_MS }, rnd);
  assert.ok(asleep.state.asleep);
  assert.ok(asleep.effects.some((e) => e.type === 'sleep'));
  const quiet = reduce(asleep.state, { type: 'tick', now: T0 + TIMING.NAG_AFTER_MS * 3 }, rnd);
  assert.equal(says(quiet.effects).length, 0, 'a sleeping gnome does not nag');
  const awake = reduce(asleep.state, { type: 'activity', now: T0 + TIMING.SLEEP_AFTER_MS + MIN }, rnd);
  assert.ok(!awake.state.asleep);
  assert.ok(awake.effects.some((e) => e.type === 'wake'));
});

test('pokes in quick succession make the gnome angrier, up to the top level, then it cools down', () => {
  let state = start();
  const levels = [];
  for (let i = 0; i < 5; i += 1) {
    const r = reduce(state, { type: 'poke', now: T0 + i * 500 }, rnd);
    state = r.state;
    levels.push(r.effects.find((e) => e.type === 'angry').level);
    assert.equal(says(r.effects)[0].category, 'angry');
  }
  assert.deepEqual(levels, [1, 2, 3, 3, 3]);
  const later = reduce(state, { type: 'poke', now: T0 + MIN }, rnd);
  assert.equal(later.effects.find((e) => e.type === 'angry').level, 1);
});

test('poking a sleeping gnome wakes it up angry', () => {
  const asleep = reduce(start(), { type: 'tick', now: T0 + TIMING.SLEEP_AFTER_MS }, rnd).state;
  const { state, effects } = reduce(asleep, { type: 'poke', now: T0 + TIMING.SLEEP_AFTER_MS + 1 }, rnd);
  assert.ok(!state.asleep);
  assert.equal(says(effects)[0].category, 'woken');
  assert.ok(effects.some((e) => e.type === 'angry'));
});

test('a random jab comes when its time is due, not right after the gnome spoke', () => {
  const quiet = initialState(T0, {}, () => 0);  // the earliest jab: JAB_MIN_MS after start, before the nag time
  const due = quiet.nextJabAt;
  const awake = reduce(quiet, { type: 'activity', now: due - 1 }, rnd).state;
  assert.equal(says(reduce(awake, { type: 'tick', now: due }, rnd).effects)[0].category, 'jab');
  const spoke = reduce(awake, { type: 'poke', now: due - 1 }, rnd).state;
  assert.equal(says(reduce(spoke, { type: 'tick', now: due }, rnd).effects).length, 0);
});

test('a hidden gnome is silent but still counts leads, and comes back on the command', () => {
  const hidden = reduce(start(), { type: 'command', now: T0, command: 'hide' }, rnd);
  assert.ok(hidden.state.hidden);
  assert.ok(hidden.effects.some((e) => e.type === 'leave'));
  assert.equal(says(hidden.effects)[0].category, 'leaving');
  const worked = work(hidden.state, 1);
  assert.equal(worked.state.count, 1);
  assert.equal(says(worked.effects).length, 0);
  const later = T0 + TIMING.NAG_AFTER_MS * 2;
  assert.deepEqual(reduce(worked.state, { type: 'tick', now: later }, rnd).effects, []);
  assert.deepEqual(reduce(worked.state, { type: 'poke', now: later }, rnd).effects, []);
  const back = reduce(worked.state, { type: 'command', now: later, command: 'show' }, rnd);
  assert.ok(!back.state.hidden);
  assert.ok(back.effects.some((e) => e.type === 'enter'));
  assert.equal(says(back.effects)[0].category, 'back');
  assert.equal(says(reduce(back.state, { type: 'tick', now: later + 1 }, rnd).effects).length, 0, 'no nag right after coming back');
});

test('hiding a sleeping gnome wakes it first', () => {
  const asleep = reduce(start(), { type: 'tick', now: T0 + TIMING.SLEEP_AFTER_MS }, rnd).state;
  const { effects } = reduce(asleep, { type: 'command', now: T0 + TIMING.SLEEP_AFTER_MS, command: 'hide' }, rnd);
  assert.deepEqual(effects.map((e) => e.type), ['wake', 'say', 'leave']);
});

test('hiding twice does nothing, showing a shown gnome makes it answer', () => {
  const hidden = reduce(start(), { type: 'command', now: T0, command: 'hide' }, rnd).state;
  assert.deepEqual(reduce(hidden, { type: 'command', now: T0, command: 'hide' }, rnd).effects, []);
  assert.equal(says(reduce(start(), { type: 'command', now: T0, command: 'show' }, rnd).effects)[0].category, 'alreadyHere');
});

test('the counter starts again on a new day', () => {
  assert.equal(start({ day: '2026-11-22', count: 7, counted: ['f/1'] }).count, 0);
  assert.equal(start({ day: '2026-11-23', count: 7, counted: ['f/1'] }).count, 7);
  const tomorrow = new Date(2026, 10, 24, 9, 0).getTime();
  const r = reduce(work(start(), 1).state, { type: 'tick', now: tomorrow }, rnd);
  assert.equal(r.state.count, 0);
  assert.deepEqual(r.state.counted, []);
});

test('the hidden choice survives a new day', () => {
  assert.ok(start({ day: '2026-11-01', hidden: true }).hidden);
});

test('the same phrase does not come twice in a row', () => {
  let state = start();
  let last = '';
  for (const x of [0, 0, 0, 0.99, 0.99, 0.5, 0.5]) {
    const r = reduce(state, { type: 'status', now: T0, key: 'f/1', from: 'written', to: 'almost' }, () => x);
    state = r.state;
    const text = says(r.effects)[0].text;
    assert.notEqual(text, last);
    last = text;
  }
});

test('reduce does not mutate the state it is given', () => {
  const frozen = Object.freeze({ ...start(), counted: Object.freeze([]), lastSaid: Object.freeze({}) });
  assert.doesNotThrow(() => work(frozen, 1));
  assert.doesNotThrow(() => reduce(frozen, { type: 'poke', now: T0 }, rnd));
});

test('memoryOf keeps what is saved between visits', () => {
  const hidden = reduce(start(), { type: 'command', now: T0, command: 'hide' }, rnd).state;
  assert.deepEqual(memoryOf(work(hidden, 3).state), { day: '2026-11-23', count: 1, counted: ['f/3'], hidden: true });
});

test('bad saved memory is ignored', () => {
  const state = start({ day: 5, count: 'x', counted: 'nope', hidden: 'yes' });
  assert.equal(state.count, 0);
  assert.deepEqual(state.counted, []);
  assert.equal(state.hidden, false);
});
