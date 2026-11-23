import { test } from 'node:test';
import assert from 'node:assert/strict';
import { initialState, reduce, TIMING } from '../../leadbombing/web/static/app/gnome/brain.js';
import { ACTIONS, actionPhrases } from '../../leadbombing/web/static/app/gnome/actions.js';

const T0 = new Date(2026, 10, 23, 10, 0, 0).getTime();
const SEC = 1000;
const lucky = () => 0;       // random() → 0: every chance passes
const unlucky = () => 0.99;  // random() → 0.99: low-key actions stay uncommented
const start = () => initialState(T0, {}, lucky);
const act = (state, action, now = T0, extra = {}, random = lucky) => reduce(state, { type: 'action', now, action, ...extra }, random);
const said = (effects) => effects.filter((e) => e.type === 'say');

test('every action has at least three different phrases', () => {
  for (const [id, rule] of Object.entries(ACTIONS)) {
    for (const detail of [{}, { count: 0 }, { count: 7 }, { value: 5 }, { value: 1 }, { value: 3 }]) {
      const list = actionPhrases(id, detail);
      assert.ok(list.length >= 3, id + ' ' + JSON.stringify(detail));
      assert.equal(new Set(list).size, list.length, id + ' has repeats');
    }
    assert.ok(['happy', 'talk', 'grumpy', 'angry', 'sad'].includes(rule.mood), id);
  }
});

test('picking the bathhouse sphere gets a steam joke', () => {
  const s = said(act(start(), 'sphere:bani').effects);
  assert.equal(s.length, 1);
  assert.ok(actionPhrases('sphere:bani', {}).includes(s[0].text));
  assert.ok(actionPhrases('sphere:bani', {}).some((p) => /попар/i.test(p)));
});

test('starting a search is commented, and the first phrase list has «лиды закончились»', () => {
  assert.ok(actionPhrases('search:start', {}).some((p) => /лиды закончились/i.test(p)));
  assert.equal(said(act(start(), 'search:start').effects).length, 1);
});

test('a finished search names the number of leads found, an empty one says so', () => {
  assert.match(said(act(start(), 'search:done', T0, { count: 23 }).effects)[0].text, /23/);
  assert.ok(actionPhrases('search:done', { count: 0 }).every((p) => !/\d+ лид/.test(p)));
});

test('the same action is not commented again within its repeat time', () => {
  const first = act(start(), 'sphere:auto');
  const soon = act(first.state, 'sphere:auto', T0 + 20 * SEC);
  assert.equal(said(soon.effects).length, 0);
  const later = act(soon.state, 'sphere:auto', T0 + TIMING.ACTION_REPEAT_MS + 1);
  assert.equal(said(later.effects).length, 1);
});

test('a low-key action is skipped right after the gnome spoke and when the chance fails', () => {
  const spoke = act(start(), 'sphere:bani').state;
  assert.equal(said(act(spoke, 'card', T0 + SEC).effects).length, 0, 'too soon after the last phrase');
  assert.equal(said(act(start(), 'card', T0, {}, unlucky).effects).length, 0, 'chance failed');
  assert.equal(said(act(start(), 'card').effects).length, 1);
});

test('an important action is commented even right after another phrase', () => {
  const spoke = act(start(), 'sphere:bani').state;
  assert.equal(said(act(spoke, 'search:start', T0 + SEC).effects).length, 1);
});

test('an unknown action is ignored but still counts as activity', () => {
  const { state, effects } = act(start(), 'nonsense', T0 + 3 * SEC);
  assert.deepEqual(effects, []);
  assert.equal(state.lastActivityAt, T0 + 3 * SEC);
});

test('a work action resets the nag timer, a page change does not', () => {
  const searched = act(start(), 'search:start', T0 + 9 * 60 * SEC).state;
  const awake = reduce(searched, { type: 'activity', now: T0 + TIMING.NAG_AFTER_MS }, lucky).state;
  assert.ok(said(reduce(awake, { type: 'tick', now: T0 + TIMING.NAG_AFTER_MS }, lucky).effects).every((e) => e.category !== 'nag'));
  const paged = act(start(), 'page:docs', T0 + 9 * 60 * SEC).state;
  const awake2 = reduce(paged, { type: 'activity', now: T0 + TIMING.NAG_AFTER_MS }, lucky).state;
  assert.equal(said(reduce(awake2, { type: 'tick', now: T0 + TIMING.NAG_AFTER_MS }, lucky).effects)[0].category, 'nag');
});

test('a hidden gnome does not comment actions', () => {
  const hidden = reduce(start(), { type: 'command', now: T0, command: 'hide' }, lucky).state;
  assert.deepEqual(act(hidden, 'search:start', T0 + 60 * SEC).effects, []);
});

test('an action wakes a sleeping gnome', () => {
  const asleep = reduce(start(), { type: 'tick', now: T0 + TIMING.SLEEP_AFTER_MS }, lucky).state;
  const { state, effects } = act(asleep, 'sphere:dental', T0 + TIMING.SLEEP_AFTER_MS + SEC);
  assert.ok(!state.asleep);
  assert.equal(effects[0].type, 'wake');
});

test('no activity for a while: «чё завис» once, before it falls asleep', () => {
  const stare = reduce(start(), { type: 'tick', now: T0 + TIMING.STARE_AFTER_MS }, lucky);
  assert.equal(said(stare.effects)[0].category, 'stare');
  assert.equal(said(reduce(stare.state, { type: 'tick', now: T0 + TIMING.STARE_AFTER_MS + 30 * SEC }, lucky).effects).length, 0);
  const moved = reduce(stare.state, { type: 'activity', now: T0 + TIMING.STARE_AFTER_MS + 40 * SEC }, lucky).state;
  const again = reduce(moved, { type: 'tick', now: T0 + TIMING.STARE_AFTER_MS * 2 + 40 * SEC }, lucky);
  assert.equal(said(again.effects)[0].category, 'stare', 'after activity it can stare again');
  assert.ok(TIMING.STARE_AFTER_MS < TIMING.SLEEP_AFTER_MS);
});
