/* The 3D gnome: a red hat, a nose, a white beard, a green body and dark boots, built from Three.js shapes (no model file).
   createGnomeScene(canvas, opts) → controls: mood(), sleep(), wake(), angry(level), leave(), enter(), pause(), resume(), dispose().
   Each frame onFrame gets where the gnome is in canvas pixels (head x/y, half width), for the bubble and the click area.
   With reduced motion the gnome does not walk, breathe or shake: only its pose changes. */
import {
  Scene, PerspectiveCamera, WebGLRenderer, Group, Mesh, MeshStandardMaterial, MeshBasicMaterial, SphereGeometry, ConeGeometry,
  CylinderGeometry, LatheGeometry, CapsuleGeometry, TorusGeometry, CircleGeometry, Vector2, Vector3, HemisphereLight,
  DirectionalLight, CanvasTexture, Color, SRGBColorSpace, MathUtils,
} from '../vendor/three-gnome-0.187.0.min.js';

const COLORS = { hat: '#c8322c', hatDark: '#a92822', skin: '#f1b79c', beard: '#f4f2ee', body: '#3f8a3c', boot: '#3a2721',
  angryNose: '#e2483f' };
const WANDER_X = 0.5;          // how far the gnome walks from the centre of its corner, in scene units
const WALK_SPEED = 0.55;        // units per second
const OFFSTAGE_X = 2.6;         // where it walks to when it leaves
const EXIT_SPEED = 1.5;         // leaving and coming back are brisk
const WANDER_MIN_S = 6;
const WANDER_MAX_S = 14;
const ANGRY_BASE_S = 1.1;
const HAPPY_S = 1.2;
const MAX_DPR = 2;
const HALF_WIDTH = 0.66;        // the gnome's half width in scene units, for the click area
const HEAD_Y = 3.3;

const mat = (color, extra = {}) => new MeshStandardMaterial({ color, roughness: 0.85, metalness: 0, ...extra });
const lathe = (points, segments = 48) => new LatheGeometry(points.map(([x, y]) => new Vector2(x, y)), segments);

/* Hair strands for the beard: thin vertical light and shadow lines, used as the colour and bump map. */
function beardTexture() {
  const c = document.createElement('canvas');
  c.width = 256;
  c.height = 256;
  const g = c.getContext('2d');
  g.fillStyle = '#f4f2ee';
  g.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 260; i += 1) {
    const x = Math.random() * 256;
    g.strokeStyle = Math.random() < 0.35 ? 'rgba(190,186,180,.28)' : 'rgba(255,255,255,.85)';
    g.lineWidth = 0.5 + Math.random();
    g.beginPath();
    g.moveTo(x, 0);
    g.bezierCurveTo(x + 6, 90, x - 6, 170, x + (Math.random() - 0.5) * 10, 256);
    g.stroke();
  }
  const t = new CanvasTexture(c);
  t.colorSpace = SRGBColorSpace;
  return t;
}

/* The soft round shadow under the gnome. */
function shadowTexture() {
  const c = document.createElement('canvas');
  c.width = 128;
  c.height = 128;
  const g = c.getContext('2d');
  const grad = g.createRadialGradient(64, 64, 4, 64, 64, 64);
  grad.addColorStop(0, 'rgba(0,0,0,.42)');
  grad.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = grad;
  g.fillRect(0, 0, 128, 128);
  return new CanvasTexture(c);
}

function buildBody(parts) {
  const body = new Mesh(lathe([[0, 0.1], [0.55, 0.12], [0.64, 0.35], [0.63, 0.7], [0.56, 1.0], [0.4, 1.22], [0, 1.28]]),
    mat(COLORS.body));
  const boots = [-1, 1].map((side) => {
    const boot = new Mesh(new SphereGeometry(0.25, 32, 16), mat(COLORS.boot, { roughness: 0.6 }));
    boot.scale.set(1.2, 0.6, 1.5);
    boot.position.set(side * 0.32, 0.13, 0.2);
    return boot;
  });
  const arms = [-1, 1].map((side) => {
    const arm = new Group();
    const sleeve = new Mesh(new CapsuleGeometry(0.12, 0.26, 8, 16), mat(COLORS.body));
    const hand = new Mesh(new SphereGeometry(0.11, 20, 12), mat(COLORS.skin));
    hand.position.y = -0.24;
    arm.add(sleeve, hand);
    arm.position.set(side * 0.66, 0.74, 0.04);
    arm.rotation.z = side * 0.18;
    return arm;
  });
  parts.root.add(body, ...boots, ...arms);
  return { body, arms };
}

function buildFace(parts) {
  const head = new Mesh(new SphereGeometry(0.45, 32, 20), mat(COLORS.skin));
  head.position.set(0, 1.2, 0.1);
  const beardMap = beardTexture();
  const beard = new Mesh(lathe([[0, 0], [0.14, 0.1], [0.34, 0.34], [0.52, 0.68], [0.6, 0.94], [0.57, 1.08], [0.42, 1.17], [0, 1.2]], 64),
    mat(COLORS.beard, { map: beardMap, bumpMap: beardMap, bumpScale: 0.7, roughness: 1 }));
  beard.scale.set(1.04, 1.1, 0.5);
  beard.position.set(0, 0.04, 0.42);
  const mustache = [-1, 1].map((side) => {
    const m = new Mesh(new SphereGeometry(0.21, 24, 16), mat(COLORS.beard, { map: beardMap, roughness: 1 }));
    m.scale.set(1.6, 0.5, 0.6);
    m.position.set(side * 0.24, 1.22, 0.68);
    m.rotation.z = side * -0.3;
    return m;
  });
  const noseMat = mat(COLORS.skin, { roughness: 0.55 });
  const nose = new Mesh(new SphereGeometry(0.19, 32, 20), noseMat);
  nose.scale.set(1.15, 1, 1);
  nose.position.set(0, 1.3, 0.74);
  parts.root.add(head, beard, ...mustache, nose);
  return { beard, nose, noseMat };
}

function buildHat(parts) {
  const hatMat = mat(COLORS.hat, { roughness: 0.75 });
  const brim = new Mesh(new TorusGeometry(0.57, 0.085, 16, 64), mat(COLORS.hatDark, { roughness: 0.75 }));
  brim.rotation.x = Math.PI / 2;
  brim.position.y = 1.38;
  const lower = new Mesh(new CylinderGeometry(0.45, 0.6, 0.62, 64, 1, true), hatMat);
  lower.position.y = 1.68;
  const tip = new Group();          // the upper hat bends at this pivot: droops when asleep, shakes when angry
  tip.position.y = 1.98;
  const cone = new Mesh(new ConeGeometry(0.455, 1.25, 64), hatMat);
  cone.position.y = 0.6;
  tip.add(cone);
  parts.root.add(brim, lower, tip);
  return { tip };
}

function buildShadow() {
  const shadow = new Mesh(new CircleGeometry(0.95, 32), new MeshBasicMaterial({ map: shadowTexture(), transparent: true, depthWrite: false }));
  shadow.rotation.x = -Math.PI / 2;
  shadow.position.y = 0.005;
  return shadow;
}

function buildGnome() {
  const root = new Group();
  const parts = { root };
  const built = { root, ...buildBody(parts), ...buildFace(parts), ...buildHat(parts), shadow: buildShadow() };
  return built;
}

function buildStage(canvas) {
  const renderer = new WebGLRenderer({ canvas, alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, MAX_DPR));
  renderer.outputColorSpace = SRGBColorSpace;
  const scene = new Scene();
  const camera = new PerspectiveCamera(30, 1, 0.1, 50);
  camera.position.set(0, 1.85, 7.3);
  camera.lookAt(0, 1.62, 0);
  scene.add(new HemisphereLight('#ffffff', '#b9a6a0', 1.5));
  const key = new DirectionalLight('#fff4ea', 2.4);
  key.position.set(3, 5, 5);
  const rim = new DirectionalLight('#ffe3e0', 0.9);
  rim.position.set(-4, 3, -3);
  scene.add(key, rim);
  return { renderer, scene, camera };
}

const ease = (current, target, rate, dt) => current + (target - current) * Math.min(1, rate * dt);

/* Moods and moves over time: the loop reads this plain state each frame. */
function initialMotion(reduced) {
  return { x: 0, targetX: 0, speed: WALK_SPEED, mode: 'idle', modeUntil: 0, anger: 0, nextWanderAt: reduced ? Infinity : 4,
    onArrive: null, reduced };
}

export function createGnomeScene(canvas, { reducedMotion = false, onFrame = () => {} } = {}) {
  const { renderer, scene, camera } = buildStage(canvas);
  const g = buildGnome();
  scene.add(g.root, g.shadow);
  const baseNose = new Color(COLORS.skin);
  const angryNose = new Color(COLORS.angryNose);
  const headPoint = new Vector3();
  const sidePoint = new Vector3();
  let lastReport = '';
  let m = initialMotion(reducedMotion);
  let clock = 0;
  let last = performance.now();
  let frame = 0;

  const resize = () => {
    const { clientWidth: w, clientHeight: h } = canvas;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  const observer = new ResizeObserver(resize);
  observer.observe(canvas);
  resize();

  const set = (patch) => { m = { ...m, ...patch }; };
  const walkTo = (x, speed = WALK_SPEED) => new Promise((resolve) => {
    if (m.reduced) { set({ x, targetX: x }); resolve(); return; }
    set({ targetX: x, speed, onArrive: resolve });
  });

  function wander() {
    if (m.mode !== 'idle' || m.reduced) return;
    set({ targetX: MathUtils.randFloat(-WANDER_X, WANDER_X), speed: WALK_SPEED, nextWanderAt: clock + MathUtils.randFloat(WANDER_MIN_S, WANDER_MAX_S) });
  }

  function animate(dt) {
    if (clock >= m.nextWanderAt) wander();
    const timed = m.modeUntil && clock >= m.modeUntil;
    if (timed) set({ mode: 'idle', modeUntil: 0, anger: 0 });
    const moving = Math.abs(m.targetX - m.x) > 0.01 && m.mode !== 'sleep';
    const step = Math.sign(m.targetX - m.x) * Math.min(Math.abs(m.targetX - m.x), m.speed * dt);
    if (moving) set({ x: m.x + step });
    else if (m.onArrive) { const done = m.onArrive; set({ onArrive: null }); done(); }
    pose(dt, moving, step);
  }

  function pose(dt, moving, step) {
    const r = g.root;
    const still = m.reduced;
    const asleep = m.mode === 'sleep';
    const angry = m.mode === 'angry';
    const happy = m.mode === 'happy';
    const shake = angry && !still ? Math.sin(clock * 42) * 0.05 * m.anger : 0;
    const hop = happy && !still ? Math.abs(Math.sin(clock * 9)) * 0.28 : 0;
    const stomp = angry && !still ? Math.abs(Math.sin(clock * 14)) * 0.06 * m.anger : 0;
    const bob = moving && !still ? Math.abs(Math.sin(clock * 11)) * 0.06 : 0;
    r.position.set(m.x + shake, hop + stomp + bob, 0);
    g.shadow.position.x = m.x;
    g.shadow.scale.setScalar(1 - (hop + bob) * 0.8);
    const facing = moving ? Math.sign(step) * 0.7 : 0;
    r.rotation.y = ease(r.rotation.y, facing, 6, dt);
    r.rotation.z = angry && !still ? Math.sin(clock * 30) * 0.04 * m.anger : ease(r.rotation.z, moving && !still ? Math.sin(clock * 11) * 0.06 : 0, 8, dt);
    r.rotation.x = ease(r.rotation.x, asleep ? 0.16 : 0, 2, dt);
    const breathe = still ? 0 : Math.sin(clock * (asleep ? 1.1 : 2.2)) * (asleep ? 0.025 : 0.012);
    g.body.scale.set(1 - breathe * 0.5, 1 + breathe, 1 - breathe * 0.5);
    const tipSway = still ? 0 : Math.sin(clock * 1.4) * 0.05;
    const tipTarget = asleep ? -0.75 : angry && !still ? Math.sin(clock * 36) * 0.18 : tipSway;
    g.tip.rotation.z = angry ? tipTarget : ease(g.tip.rotation.z, tipTarget, asleep ? 1.5 : 5, dt);
    g.noseMat.color.lerp(angry ? angryNose : baseNose, Math.min(1, 6 * dt));
    g.arms.forEach((arm, i) => {
      const side = i ? 1 : -1;
      const wave = happy && !still ? Math.sin(clock * 12 + i) * 0.5 - 1.6 : angry ? -0.5 : 0;
      arm.rotation.z = ease(arm.rotation.z, side * (0.18 - wave * (happy || angry ? 1 : 0)), 8, dt);
    });
  }

  /* Where the gnome is, in canvas pixels; reported only when it moved by a pixel, so the page is not re-laid out each frame. */
  function report() {
    const { clientWidth: w, clientHeight: h } = canvas;
    headPoint.set(g.root.position.x, HEAD_Y, 0).project(camera);
    sidePoint.set(g.root.position.x + HALF_WIDTH, 0, 0).project(camera);
    const x = Math.round((headPoint.x + 1) / 2 * w);
    const pos = { x, y: Math.round((1 - headPoint.y) / 2 * h), halfWidth: Math.round((sidePoint.x + 1) / 2 * w) - x };
    const key = `${pos.x},${pos.y},${pos.halfWidth},${w},${h}`;
    if (key === lastReport) return;
    lastReport = key;
    onFrame(pos);
  }

  function loop(now) {
    const dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    clock += dt;
    animate(dt);
    renderer.render(scene, camera);
    report();
    frame = requestAnimationFrame(loop);
  }
  const resume = () => {
    if (frame) return;
    last = performance.now();
    lastReport = '';
    frame = requestAnimationFrame(loop);
  };
  const pause = () => {
    cancelAnimationFrame(frame);
    frame = 0;
  };
  resume();

  return {
    pause,
    resume,
    mood(mood) {
      if (m.mode === 'sleep' || m.mode === 'angry') return;
      if (mood === 'happy') set({ mode: 'happy', modeUntil: clock + HAPPY_S });
    },
    sleep() { set({ mode: 'sleep', modeUntil: 0, targetX: m.x, nextWanderAt: Infinity }); },
    wake() { set({ mode: 'idle', modeUntil: 0, nextWanderAt: m.reduced ? Infinity : clock + WANDER_MIN_S }); },
    angry(level) { set({ mode: 'angry', anger: level, modeUntil: clock + ANGRY_BASE_S + level * 0.4, targetX: m.x }); },
    async leave() {
      set({ mode: 'idle', modeUntil: 0, nextWanderAt: Infinity });
      await walkTo(OFFSTAGE_X, EXIT_SPEED);
    },
    async enter() {
      set({ x: OFFSTAGE_X, targetX: OFFSTAGE_X, mode: 'idle', modeUntil: 0, nextWanderAt: Infinity });
      await walkTo(0, EXIT_SPEED);
      set({ nextWanderAt: m.reduced ? Infinity : clock + WANDER_MIN_S });
    },
    dispose() {
      pause();
      observer.disconnect();
      renderer.dispose();
    },
  };
}
