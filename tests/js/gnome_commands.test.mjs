import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseCommand, normalize } from '../../leadbombing/web/static/app/gnome/commands.js';

test('normalize lowercases, folds ё, drops punctuation and extra spaces', () => {
  assert.equal(normalize('  ГНОМ,   Съёби!!! '), 'гном съеби');
});

test('the hide phrase is recognised in any case and punctuation', () => {
  for (const text of ['гном съеби', 'Гном съеби', 'ГНОМ СЪЕБИ', 'гном, съеби!', ' гном   съеби ']) {
    assert.equal(parseCommand(text), 'hide', text);
  }
});

test('the return phrase is recognised', () => {
  for (const text of ['гном вернись', 'Гном, вернись!', 'ГНОМ ВЕРНИСЬ']) assert.equal(parseCommand(text), 'show', text);
});

test('similar but different text is not a command', () => {
  for (const text of ['гномы съеби', 'гном', 'съеби', 'гном съеби пожалуйста', 'садовый гном', '', null, undefined]) {
    assert.equal(parseCommand(text), null, String(text));
  }
});
