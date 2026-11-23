/* The speech bubble over the gnome's head: one phrase at a time, the rest wait in a queue; «Z z z» while it sleeps. */
const MIN_SHOW_MS = 2600;
const MAX_SHOW_MS = 6000;
const MS_PER_CHAR = 60;
const GAP_MS = 250;
const EDGE_PX = 8;          // the bubble keeps this far from the screen edges

const showTime = (text) => Math.min(MAX_SHOW_MS, Math.max(MIN_SHOW_MS, text.length * MS_PER_CHAR));

export function createBubble(el) {
  let queue = [];
  let timer = 0;
  let speaking = false;
  let sleeping = false;

  function render(text, mood) {
    el.textContent = text;
    el.dataset.mood = mood;
    el.hidden = !text;
  }

  function next() {
    const [item, ...rest] = queue;
    queue = rest;
    if (!item) {
      speaking = false;
      render(sleeping ? 'Z z z…' : '', sleeping ? 'sleep' : '');
      return;
    }
    speaking = true;
    render(item.text, item.mood);
    timer = setTimeout(() => {
      render('', '');
      timer = setTimeout(next, GAP_MS);
    }, showTime(item.text));
  }

  return {
    say(text, mood = 'talk') {
      queue = [...queue, { text, mood }];
      if (!speaking) next();
    },
    /* A reaction that cannot wait (a poke): drops the queue and speaks now. */
    interrupt(text, mood) {
      clearTimeout(timer);
      queue = [];
      speaking = false;
      this.say(text, mood);
    },
    sleep(on) {
      sleeping = on;
      if (!speaking) render(on ? 'Z z z…' : '', on ? 'sleep' : '');
    },
    clear() {
      clearTimeout(timer);
      queue = [];
      speaking = false;
      sleeping = false;
      render('', '');
    },
    /* Follow the head: x, y in pixels inside the gnome box; the bubble stays on screen. */
    place({ x, y }) {
      const box = el.parentElement.getBoundingClientRect();
      const half = el.offsetWidth / 2;
      const left = Math.max(EDGE_PX - box.left + half, Math.min(x, window.innerWidth - EDGE_PX - box.left - half));
      el.style.left = left + 'px';
      el.style.top = y + 'px';
    },
  };
}
