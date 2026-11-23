import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PHRASES, milestonePhrases } from '../../leadbombing/web/static/app/gnome/phrases.js';

test('every category has several different phrases', () => {
  for (const [name, list] of Object.entries(PHRASES)) {
    const all = list.flat();
    assert.ok(all.length >= 4, name);
    assert.equal(new Set(all).size, all.length, name + ' has repeats');
  }
});

test('anger has three levels, each with several phrases', () => {
  assert.equal(PHRASES.angry.length, 3);
  for (const level of PHRASES.angry) assert.ok(level.length >= 3);
});

test('milestone phrases name the number with the right word form', () => {
  assert.ok(milestonePhrases(1).length >= 3);
  assert.ok(milestonePhrases(5).length >= 3);
  assert.ok(milestonePhrases(20).every((p) => p.includes('20')));
  assert.ok(milestonePhrases(20).some((p) => p.includes('20 лидов')));
  assert.ok(milestonePhrases(210).every((p) => p.includes('210')));
});
