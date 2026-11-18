/* LeadBombing PWA: login, side menu pages (search, leads, profile, settings, docs), search form, live leads table,
   saved lead folders («Лиды») with the work on each lead, lead card, export. Alpine.js + Motion. */
const POLL_MS = 900;
const SAVE_SETTINGS_MS = 800;
const TOAST_MS = 2600;
const FORM_KEY = 'lb.form';  // the form of the last search started: unsent edits are dropped when leaving the page
const PATH_KEY = 'lb.exportPath';
const THEME_KEY = 'lb.theme';
const TINT_KEY = 'lb.tintRows';  // table rows coloured by priority (on by default)
const PAGES = ['search', 'leads', 'profile', 'settings', 'docs'];
/* Work on a saved lead («Лиды»): statuses in the order of the picker, priorities from high to none. */
const STATUSES = [
  { id: 'client', title: 'Наш клиент' }, { id: 'waiting', title: 'Ожидаем ответ' },
  { id: 'no_answer', title: 'Не ответил' }, { id: 'lost', title: 'Слился' },
];
const NEW_STATUS = { id: 'new', title: 'Новый' };
/* Lead priority 0–5: set by hand on «Лиды», or assessed from the 2GIS card (leads/booking.py); 5 is the hottest. */
const PRIORITIES = [{ id: 5, short: '5', title: 'Очень высокий' }, { id: 4, short: '4', title: 'Высокий' },
  { id: 3, short: '3', title: 'Средний' }, { id: 2, short: '2', title: 'Низкий' }, { id: 1, short: '1', title: 'Очень низкий' },
  { id: 0, short: 'Нет', title: 'Не задан' }];
const SORT_NEXT = { '': 'desc', desc: 'asc', asc: '' };  // priority column: high first, low first, folder order
/* Lead card sections, top to bottom; «Работа с клиентом» holds the sub-sections. All open when a lead is opened. */
const SECTIONS = ['contacts', 'prices', 'legal', 'work'];
const SUB_SECTIONS = ['channels', 'demo', 'message', 'hook', 'comment'];
const CUSTOM = { id: 'custom', title: 'Свободный поиск', query: '', fixed_city: null,
  note: 'Свободный поиск: все фирмы из выдачи 2ГИС по вашему запросу, выгрузка как у шаблонов' };
const STATUS_TEXT = { idle: 'Не запущен', running: 'Идёт поиск', done: 'Поиск завершён', stopped: 'Поиск остановлен',
  error: 'Поиск прерван' };
const NO_FORM_ERROR = { field: '', text: '' };

/* Russian plural: plural(5, ['лид', 'лида', 'лидов']) → 'лидов'. */
function plural(n, [one, few, many]) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}
const LEAD_WORDS = ['лид', 'лида', 'лидов'];
const DATE_FORMAT = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
const REDUCED_MOTION = matchMedia('(prefers-reduced-motion: reduce)');

/* Windows (lead card, dialogs): focus moves in on open, Tab stays inside, focus goes back on close. */
const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), '
  + '[tabindex]:not([tabindex="-1"])';
const isVisible = (el) => !!el && el.isConnected && el.getClientRects().length > 0;
const focusablesIn = (root) => [...root.querySelectorAll(FOCUSABLE)].filter(isVisible);
/* flag → [window ref, fallback ref for the return when the opener is gone (e.g. a closed menu)] */
const WINDOWS = {
  selected: ['card', null], deleteOpen: ['deleteDialog', null], clearOpen: ['clearDialog', 'moreBtn'],
  exportOpen: ['exportDialog', null], saveOpen: ['saveDialog', null],
};

function loadForm(saved = store.get(FORM_KEY, {})) {
  const form = { sphere: 'bani', query: '', cities: ['moscow'], limit: 100, showChrome: false, ...saved };
  if (!Array.isArray(form.cities) || !form.cities.length) form.cities = [saved.city || 'moscow'];
  delete form.city;
  return form;
}

function cloneForm(form) {
  return loadForm(JSON.parse(JSON.stringify(form)));
}

/* Field by field: Alpine tracks property reads, not JSON.stringify. */
function sameForm(a, b) {
  return a.sphere === b.sphere && a.query === b.query && a.limit === b.limit && a.showChrome === b.showChrome
    && [...a.cities].sort().join() === [...b.cities].sort().join();
}

const store = {
  get(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode: not critical */ }
  },
};

function pageFromPath() {
  const page = location.pathname.slice(1);
  return PAGES.includes(page) ? page : 'search';
}

/* Theme: '' follows the system, 'light' / 'dark' is the user's choice (the header button or Настройки). */
const THEME_CHOICES = [{ id: 'light', title: 'Светлая' }, { id: 'dark', title: 'Тёмная' }, { id: '', title: 'Как в системе' }];
const THEME_BG = { light: '#f7f7f8', dark: '#0e0f11' };  // --bg of each theme, for the browser chrome
const DARK_QUERY = matchMedia('(prefers-color-scheme: dark)');

function applyTheme(theme) {
  if (theme) document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
  for (const meta of document.querySelectorAll('meta[name="theme-color"]')) {
    const own = meta.media.includes('dark') ? THEME_BG.dark : THEME_BG.light;
    meta.content = theme ? THEME_BG[theme] : own;
  }
}
applyTheme(store.get(THEME_KEY, ''));  // before first paint: no flash of the wrong theme

async function api(path, body, method = body === undefined ? 'GET' : 'POST') {
  const opts = { method };
  if (body !== undefined) {
    opts.headers = { 'Content-Type': 'application/json' };
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && !path.startsWith('/api/auth/')) window.dispatchEvent(new CustomEvent('lb-logout'));
  if (!res.ok || data.ok === false) {
    const err = new Error(data.error || `Ошибка сервера (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return data;
}

document.addEventListener('alpine:init', () => {
  Alpine.data('leadsApp', () => ({
    meta: { spheres: [], cities: [] },
    form: loadForm(),
    searchForm: loadForm(),  // what the table was searched with; `form` returns to it unless «Найти лиды» is pressed
    citiesOpen: false, cityFilter: '', picked: [], moreOpen: false, formError: NO_FORM_ERROR,
    status: 'idle', error: '', log: '', cursor: 0,
    params: null, resumable: false, busy: false, searchCleared: false, clearOpen: false, _hadForm: false,
    leads: [], skipped: [], filter: '', showSkipped: false,
    selected: null, card: null,
    exportOpen: false, exporting: false, exportPath: store.get(PATH_KEY, ''),
    toast: '', _toastTimer: null, _pollTimer: null,
    user: null, authChecked: false, auth: { login: '', password: '', error: '', busy: false },
    fromAccount: false, _settingsReady: false, _saveTimer: null,
    page: pageFromPath(), theme: store.get(THEME_KEY, ''), systemDark: DARK_QUERY.matches, themeChoices: THEME_CHOICES,
    folders: [], folderId: null, folderLeads: [],
    tintRows: store.get(TINT_KEY, true),
    assess: null, assessPolling: false,  // TEMP: assessment of old leads (assess_job.py)
    saveOpen: false, saving: false, saveForm: { mode: 'new', name: '', folderId: null },
    statuses: STATUSES, priorities: PRIORITIES, prioritySort: '',
    crm: null, draft: { comment: '', demoUrl: '' }, crmBusy: false, deleteOpen: false, collapsed: {},

    async init() {
      this.$watch('citiesOpen', (open) => open && this.$nextTick(() => this.$refs.cityFilter.focus()));
      // A field error goes away as soon as the field it is about changes.
      this.$watch('form.query', () => this.formError.field === 'query' && this.clearFormError());
      this.$watch('form.cities', () => this.formError.field === 'cities' && this.clearFormError());
      this.$watch('form.sphere', () => this.clearFormError());
      for (const [flag, [ref, fallback]] of Object.entries(WINDOWS)) {
        this.$watch(flag, (open, was) => {
          if (open && !was) this.focusWindow(flag, ref);
          else if (!open && was) this.returnFocus(flag, fallback);
        });
      }
      this.$watch('exportPath', () => this.saveSettings());
      // Leaving the app must not lose a settings change still waiting for the debounced save.
      window.addEventListener('pagehide', () => this.flushSettings());
      document.addEventListener('visibilitychange', () => document.visibilityState === 'hidden' && this.flushSettings());
      window.addEventListener('popstate', () => this.showPage(pageFromPath()));
      DARK_QUERY.addEventListener('change', (e) => { this.systemDark = e.matches; });
      try {
        this.user = (await api('/api/auth/me')).login;
      } catch (e) {
        if (e.status !== 401) this.auth.error = 'Сервер не отвечает. Запустите leadbombing и обновите страницу.';
      }
      this.authChecked = true;
      if (this.user) await this.boot();
    },

    async boot() {
      try {
        this.meta = await api('/api/leads/meta');
      } catch (e) {
        this.error = 'Сервер не отвечает. Запустите leadbombing и обновите страницу.';
        return;
      }
      await this.loadSettings();
      if (!this.sphere) this.form.sphere = 'bani';
      if (!this._hadForm && !this.form.query) this.form.query = this.sphere.query;  // first visit only
      this.searchForm = cloneForm(this.form);
      await this.poll();  // restore the current run after a reload
      if (!this.leads.length && !this.running && !this.searchCleared) await this.loadSaved();
      if (this.onLeads) await this.loadFolders();
    },

    async signIn() {
      this.auth.error = '';
      this.auth.busy = true;
      try {
        const r = await api('/api/auth/login', { login: this.auth.login.trim(), password: this.auth.password });
        this.user = r.login;
        this.auth.password = '';
        await this.boot();
      } catch (e) {
        this.auth.error = e.message;
      } finally {
        this.auth.busy = false;
      }
    },
    async signOut() {
      await api('/api/auth/logout', {}).catch(() => {});
      location.reload();
    },
    onLoggedOut() {
      clearTimeout(this._pollTimer);
      clearTimeout(this._saveTimer);
      this._settingsReady = false;
      this.user = null;
      this.closeCard();
      this.exportOpen = false;
      this.auth.error = 'Сессия закончилась — войдите снова';
    },

    go(page) {
      if (page === this.page) return;
      history.pushState({}, '', `/${page}`);
      this.showPage(page);
    },
    showPage(page) {
      if (page !== this.page) this.restoreForm();  // edits without «Найти лиды» do not outlive the page
      this.page = page;
      this.picked = [];
      this.filter = '';
      this.prioritySort = '';
      this.closeCard();
      if (page === 'leads') this.loadFolders();
    },
    get onLeads() { return this.page === 'leads'; },

    async fetchFolders() {
      try {
        this.folders = (await api('/api/folders')).folders;
      } catch (e) {
        if (e.status !== 401) this.notify(`Папки не загружены: ${e.message}`);
      }
    },
    async loadFolders() {
      await this.fetchFolders();
      const keep = this.folders.some((f) => f.id === this.folderId);
      const id = keep ? this.folderId : this.folders[0]?.id;
      if (id) await this.showFolder(id); else this.folderLeads = [];
      this.checkAssess();
    },
    async showFolder(id) {
      this.folderId = id;
      this.picked = [];
      this.closeCard();
      try {
        this.folderLeads = (await api(`/api/folders/${id}`)).leads;
      } catch (e) {
        this.folderLeads = [];
        if (e.status !== 401) this.notify(`Папка не загружена: ${e.message}`);
      }
    },
    get folder() { return this.folders.find((f) => f.id === this.folderId); },

    /* TEMP: one-off assessment of leads saved before the 2GIS «Забронировать» button was collected (assess_job.py).
       Remove with the «Оценить лиды» button in index.html once old folders are assessed. */
    get assessing() { return this.assess?.status === 'running'; },
    get assessLabel() { return this.assessing ? `${this.assess.done} из ${this.assess.total}` : 'Оценить лиды'; },
    get assessTitle() {
      return this.assessing ? `Остановить оценку: оценено ${this.assess.done} из ${this.assess.total}`
        : 'Оценить приоритет лидов, сохранённых до появления оценки по карточке 2ГИС';
    },
    async checkAssess() {
      try {
        this.assess = await api('/api/folders/assess/status');
        if (this.assessing) this.pollAssess();
      } catch (e) { /* the status is optional: the button still works */ }
    },
    async toggleAssess() {
      try {
        if (this.assessing) {
          this.assess = await api('/api/folders/assess/stop', {});
          return;
        }
        this.assess = await api(`/api/folders/${this.folderId}/assess`, { headless: !this.form.showChrome });
        this.pollAssess();
      } catch (e) {
        this.notify(e.message);
      }
    },
    async pollAssess() {
      if (this.assessPolling) return;  // one loop: folder loads call checkAssess again
      this.assessPolling = true;
      try {
        await this.waitAssess();
      } finally {
        this.assessPolling = false;
      }
    },
    async waitAssess() {
      while (this.assessing) {
        await new Promise((resolve) => setTimeout(resolve, POLL_MS));
        try {
          this.assess = await api('/api/folders/assess/status');
        } catch (e) {
          this.notify(`Оценка: ${e.message}`);
          return;
        }
      }
      const a = this.assess;
      if (a.status === 'error') this.notify(`Оценка прервана: ${a.error}`);
      else if (!a.total) this.notify('Все лиды в папке уже оценены');
      else this.notify(`Оценено лидов: ${a.done} из ${a.total}` + (a.errors ? `, с ошибкой: ${a.errors}` : ''));
      if (this.onLeads && a.folder_id === this.folderId) await this.showFolder(this.folderId);
    },
    get sameSphereFolders() { return this.folders.filter((f) => f.sphere === this.form.sphere); },
    async openSave() {
      await this.fetchFolders();
      const name = (this.form.query || this.sphere?.title || '').trim();
      this.saveForm = { mode: 'new', name, folderId: this.sameSphereFolders[0]?.id ?? null };
      this.saveOpen = true;
    },
    async saveLeads() {
      const body = this.saveForm.mode === 'new' ? { name: this.saveForm.name.trim() } : { folder_id: this.saveForm.folderId };
      if (this.picked.length) body.slugs = this.picked;
      this.saving = true;
      try {
        const r = await api('/api/folders/save', body);
        this.folderId = r.folder.id;
        this.saveOpen = false;
        this.notify(`В папку «${r.folder.name}» сохранено: ${r.saved} ${this.leadsWord(r.saved)}`);
      } catch (e) {
        this.notify(e.message);
      } finally {
        this.saving = false;
      }
    },
    itemUrl(slug) {
      return this.onLeads ? `/api/folders/${this.folderId}/item/${slug}` : `/api/leads/item/${slug}`;
    },
    get currentTheme() { return this.theme || (this.systemDark ? 'dark' : 'light'); },
    setTheme(theme) {
      this.theme = theme;
      store.set(THEME_KEY, theme);
      applyTheme(theme);
    },
    /* The header button picks the other theme explicitly; «Как в системе» stays in Настройки. */
    toggleTheme() { this.setTheme(this.currentTheme === 'dark' ? 'light' : 'dark'); },
    get themeToggleLabel() { return this.currentTheme === 'dark' ? 'Включить светлую тему' : 'Включить тёмную тему'; },
    get initial() { return (this.user || '?').slice(0, 1).toUpperCase(); },

    async loadSettings() {
      this._settingsReady = false;
      this._hadForm = store.get(FORM_KEY, null) !== null;
      try {
        const { settings } = await api('/api/account/settings');
        if (settings.form) this.form = loadForm(settings.form);
        this._hadForm = this._hadForm || !!settings.form;
        if (settings.exportPath) this.exportPath = settings.exportPath;
        this.searchCleared = !!settings.searchCleared;
      } catch (e) {
        if (e.status !== 401) this.notify(`Настройки не загружены: ${e.message}`);
      }
      await this.$nextTick();
      this._settingsReady = true;
    },
    settingsBody() {
      return { settings: { form: this.searchForm, exportPath: this.exportPath, searchCleared: this.searchCleared } };
    },
    /* The form of a search that was actually started becomes the one the page comes back to. */
    rememberSearch() {
      this.searchForm = cloneForm(this.form);
      store.set(FORM_KEY, this.searchForm);
      this.saveSettings();
    },
    restoreForm() {
      this.form = cloneForm(this.searchForm);
      this.citiesOpen = false;
    },
    get formChanged() { return !sameForm(this.form, this.searchForm); },
    saveSettings() {
      if (!this._settingsReady || !this.user) return;
      clearTimeout(this._saveTimer);
      this._saveTimer = setTimeout(() => {
        this._saveTimer = null;
        api('/api/account/settings', this.settingsBody())
          .catch((e) => { if (e.status !== 401) this.notify(`Настройки не сохранены: ${e.message}`); });
      }, SAVE_SETTINGS_MS);
    },
    flushSettings() {
      if (!this._saveTimer) return;
      clearTimeout(this._saveTimer);
      this._saveTimer = null;
      fetch('/api/account/settings', {  // keepalive: the request survives the page being closed
        method: 'POST', keepalive: true, headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this.settingsBody()),
      }).catch(() => { /* the form is also kept in localStorage */ });
    },
    async loadSaved() {
      try {
        const { leads } = await api('/api/account/leads');
        // The same firm can be saved under several spheres: keep its newest row, the table is keyed by slug.
        const fresh = leads.filter((l, i) => leads.findIndex((x) => x.slug === l.slug) === i);
        this.leads = fresh.map((l) => ({ ...l, has_photo: false }));  // photos stay in the run folder
        this.fromAccount = this.leads.length > 0;
      } catch (e) {
        if (e.status !== 401) this.notify(`Лиды из кабинета не загружены: ${e.message}`);
      }
    },

    get sphere() {
      return this.form.sphere === CUSTOM.id ? CUSTOM : this.meta.spheres.find((s) => s.id === this.form.sphere);
    },
    get searchCities() { return this.sphere?.fixed_city ? [this.sphere.fixed_city] : this.form.cities; },
    get citiesLabel() {
      const names = this.searchCities.map((code) => this.meta.cities.find((c) => c.code === code)?.name || code);
      if (!names.length) return 'Выберите города';
      return names.length > 2 ? `${names.slice(0, 2).join(', ')} +${names.length - 2}` : names.join(', ');
    },
    get filteredCities() {
      const q = this.cityFilter.trim().toLowerCase();
      const list = q ? this.meta.cities.filter((c) => c.name.toLowerCase().includes(q)) : this.meta.cities;
      const on = new Set(this.form.cities);
      return [...list.filter((c) => on.has(c.code)), ...list.filter((c) => !on.has(c.code))];
    },
    get list() { return this.onLeads ? this.folderLeads : this.leads; },
    get exportCount() { return this.picked.length || this.list.length; },
    /* Export: a saved folder with leads, or a new search (leads of past searches come back only for viewing). */
    get canExport() { return this.onLeads ? this.folderLeads.length > 0 : this.leads.length > 0 && !this.fromAccount; },
    get allVisiblePicked() {
      return this.visible.length > 0 && this.visible.every((l) => this.picked.includes(l.slug));
    },
    get running() { return this.status === 'running'; },
    get isBani() { return (this.onLeads ? this.folder?.sphere : this.form.sphere) === 'bani'; },
    get pricesTitle() { return this.isBani ? 'Залы' : 'Услуги'; },
    get statusText() { return STATUS_TEXT[this.status]; },
    get statusHint() { return this.canResume ? 'можно продолжить с того же места' : ''; },
    leadsWord(n) { return plural(n, LEAD_WORDS); },
    get sphereChoices() { return [...this.meta.spheres, CUSTOM]; },
    get visible() {
      const q = this.filter.trim().toLowerCase();
      const found = q ? this.list.filter((l) => `${l.name} ${l.district}`.toLowerCase().includes(q)) : this.list;
      if (!this.prioritySort) return found;
      const sign = this.prioritySort === 'desc' ? -1 : 1;
      return [...found].sort((a, b) => sign * ((a.priority || 0) - (b.priority || 0)));  // stable: ties keep folder order
    },
    get skippedByReason() {
      const counts = {};
      for (const s of this.skipped) counts[s.reason] = (counts[s.reason] || 0) + 1;
      return Object.entries(counts).sort((a, b) => b[1] - a[1]);
    },

    pickSphere(s) {
      this.form.sphere = s.id;
      this.form.query = s.query;
    },
    freeSearch() {
      if (!this.running && this.form.sphere !== CUSTOM.id) this.form.sphere = CUSTOM.id;
    },
    togglePick(slug) {
      this.picked = this.picked.includes(slug) ? this.picked.filter((x) => x !== slug) : [...this.picked, slug];
    },
    toggleAll(on) {
      const visible = new Set(this.visible.map((l) => l.slug));
      const rest = this.picked.filter((x) => !visible.has(x));
      this.picked = on ? [...rest, ...visible] : rest;
    },

    focusWindow(flag, ref) {
      this._openers = { ...this._openers, [flag]: document.activeElement };
      this.$nextTick(() => {
        const win = this.$refs[ref];
        if (!win) return;
        const first = [...win.querySelectorAll('[data-autofocus]')].find(isVisible) || (flag === 'selected' ? win : focusablesIn(win)[0]);
        (first || win).focus({ preventScroll: flag === 'selected' });
      });
    },
    returnFocus(flag, fallback) {
      const opener = this._openers?.[flag];
      this.$nextTick(() => {
        const target = isVisible(opener) ? opener : this.$refs[fallback];
        if (isVisible(target)) target.focus();
      });
    },
    trapTab(e) {
      const items = focusablesIn(e.currentTarget);
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && (active === first || active === e.currentTarget)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && (active === last || active === e.currentTarget)) { e.preventDefault(); first.focus(); }
    },

    /* A wrong form field: the message goes under the form, the field is marked and focused. */
    showFormError(field, text) {
      this.formError = { field, text };
      this.$nextTick(() => this.$refs[field]?.focus());
    },
    clearFormError() { this.formError = NO_FORM_ERROR; },

    /* «Ещё» menu over the results: focus goes into the menu and back to its button. */
    toggleMore() {
      this.moreOpen = !this.moreOpen;
      if (this.moreOpen) this.$nextTick(() => this.$refs.moreMenu.querySelector('[role=menuitem]:not([disabled])')?.focus());
    },
    closeMore() {
      if (!this.moreOpen) return;
      this.moreOpen = false;
      this.$refs.moreBtn.focus();
    },

    async start() {
      this.error = '';
      this.clearFormError();
      this.citiesOpen = false;
      if (this.form.sphere === CUSTOM.id && !this.form.query.trim()) {
        this.showFormError('query', 'Введите, что искать в 2ГИС, или выберите сферу');
        return;
      }
      if (!this.searchCities.length) {
        this.showFormError('cities', 'Выберите хотя бы один город');
        return;
      }
      try {
        await api('/api/leads/start', {
          sphere: this.form.sphere, query: this.form.query || this.sphere?.query, cities: this.searchCities,
          limit: this.form.limit, headless: !this.form.showChrome,
        });
      } catch (e) {
        this.error = e.message;
        return;
      }
      this.leads = []; this.skipped = []; this.picked = []; this.cursor = 0; this.fromAccount = false; this.closeCard();
      this.status = 'running';
      this.searchCleared = false;
      this.rememberSearch();
      this.schedulePoll();
    },

    /* Continue a stopped or failed run from the city and page where it ended; the table keeps what was found. */
    async resume() {
      this.error = '';
      this.citiesOpen = false;
      try {
        await api('/api/leads/resume', { limit: this.form.limit, headless: !this.form.showChrome });
      } catch (e) {
        this.error = e.message;
        return;
      }
      this.status = 'running';
      this.rememberSearch();  // a new limit or Chrome window choice is part of the search now
      this.schedulePoll();
    },

    async stop() {
      this.status = 'stopped';  // the server stops at once; polling picks up the firm that was in progress
      await api('/api/leads/stop', {}).catch((e) => { this.error = e.message; });
      this.schedulePoll();
    },

    async clearLeads() {
      try {
        await api('/api/leads/clear', {});
      } catch (e) {
        this.notify(e.message);
        return;
      }
      this.clearOpen = false;
      this.leads = []; this.skipped = []; this.picked = []; this.cursor = 0; this.fromAccount = false; this.closeCard();
      this.status = 'idle'; this.params = null; this.resumable = false; this.log = ''; this.error = '';
      this.searchCleared = true;  // leads of earlier runs are not brought back from the account either
      this.resetForm();  // an empty table has no search behind it: the filters start over too
    },
    /* Default filters (bathhouses in Moscow); the Chrome window choice is a display setting and stays. */
    defaultForm() {
      const form = loadForm({ showChrome: this.searchForm.showChrome });
      form.query = this.meta.spheres.find((s) => s.id === form.sphere)?.query || '';
      return form;
    },
    resetForm() {
      this.form = this.defaultForm();
      this.rememberSearch();
    },
    get filtersSet() { return !sameForm(this.searchForm, this.defaultForm()) || this.formChanged; },

    /* The run in the table matches the form: same sphere, query and cities (the limit may change on resume). */
    get sameRun() {
      const p = this.params;
      if (!p) return false;
      const query = (this.form.query || this.sphere?.query || '').trim();
      const codes = (list) => [...list].sort().join(',');
      return p.sphere === this.form.sphere && p.query === query && codes(p.cities) === codes(this.searchCities);
    },
    get canResume() { return !this.running && this.resumable && this.sameRun; },
    get searchLabel() {
      if (this.running) return 'Остановить';
      return this.canResume ? 'Продолжить поиск' : 'Найти лиды';
    },
    submitSearch() {
      if (this.running) return this.stop();
      return this.canResume ? this.resume() : this.start();
    },
    get canClear() {
      return !this.running && !this.busy
        && (this.leads.length > 0 || this.skipped.length > 0 || !!this.params || this.filtersSet);
    },
    /* What the table holds: «query» · sphere · cities · limit of its run. */
    get runLabel() {
      const p = this.params;
      if (!p || this.fromAccount) return '';
      const sphere = p.sphere === CUSTOM.id ? null : this.meta.spheres.find((s) => s.id === p.sphere);
      const names = p.cities.map((code) => this.meta.cities.find((c) => c.code === code)?.name || code);
      const where = names.length > 3 ? `${names.slice(0, 3).join(', ')} +${names.length - 3}` : names.join(', ');
      return [`«${p.query}»`, sphere?.title, where, `до ${p.limit} на город`].filter(Boolean).join(' · ');
    },

    schedulePoll() {
      clearTimeout(this._pollTimer);
      this._pollTimer = setTimeout(() => this.poll(), POLL_MS);
    },

    async poll() {
      let s;
      try {
        s = await api(`/api/leads/status?cursor=${this.cursor}`);
      } catch (e) {
        if (e.status === 401) return;
        this.error = 'Нет связи с сервером: ' + e.message;
        return this.schedulePoll();
      }
      if (this.cursor === 0) { this.leads = []; this.skipped = []; }
      for (const ev of s.events) {
        if (ev.type === 'skip') { this.skipped.push(ev); continue; }
        const at = this.leads.findIndex((l) => l.slug === ev.slug);
        if (at >= 0) this.leads.splice(at, 1, ev); else this.leads.push(ev);
      }
      this.cursor = s.cursor;
      this.status = s.status;
      this.params = s.params;
      this.resumable = s.resumable;
      this.busy = s.busy;
      this.log = (s.log || '').replace(/^\d\d:\d\d:\d\d\s*/, '');
      if (s.error) this.error = s.error;
      if (this.running || this.busy) this.schedulePoll();
      else if (s.status === 'done' && s.events.length) this.notify(`Поиск завершён: ${this.leads.length} ${this.leadsWord(this.leads.length)}`);
    },

    appear(el) {
      if (window.Motion && !REDUCED_MOTION.matches) {
        Motion.animate(el, { opacity: [0, 1], transform: ['translateY(6px)', 'none'] }, { duration: 0.35 });
      }
    },
    /* 2GIS gives ISO dates (2025-01-21): show them the Russian way; anything else stays as it came. */
    formatDate(value) {
      const date = /^\d{4}-\d{2}-\d{2}/.test(value || '') ? new Date(value) : null;
      return date && !Number.isNaN(date.getTime()) ? DATE_FORMAT.format(date) : value;
    },
    /* Radiogroups (spheres, folders, theme, status, priority): arrow keys pick the next or previous choice. */
    radioKeys(e) {
      const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
      if (!step) return;
      const radios = [...e.currentTarget.querySelectorAll('[role=radio]:not([disabled])')];
      const at = radios.indexOf(document.activeElement);
      if (at < 0) return;
      e.preventDefault();
      const next = radios[(at + step + radios.length) % radios.length];
      next.focus();
      next.click();
    },

    async openCard(slug) {
      this.selected = slug;
      this.card = null;
      this.collapsed = {};
      try {
        const card = await api(this.itemUrl(encodeURIComponent(slug)));
        if (this.selected !== slug) return;  // another lead was opened meanwhile
        this.card = card;
        this.crm = card.crm || null;  // kept apart from the card: a change does not re-render the card and its photo
        this.draft = { comment: this.crm?.comment || '', demoUrl: this.crm?.demo_url || '' };
      } catch (e) {
        this.closeCard();
        this.notify(e.message);
      }
    },
    closeCard() { this.selected = null; this.card = null; this.crm = null; this.deleteOpen = false; },

    /* Card sections fold one by one or all at once (the icon in the card header). */
    isOpen(key) { return !this.collapsed[key]; },
    toggleSection(key) { this.collapsed = { ...this.collapsed, [key]: !this.collapsed[key] }; },
    get allCollapsed() { return SECTIONS.every((k) => this.collapsed[k]); },
    toggleSections() {
      this.collapsed = this.allCollapsed ? {} : Object.fromEntries([...SECTIONS, ...SUB_SECTIONS].map((k) => [k, true]));
    },

    /* Work on a saved lead: status, priority, contacted channels, demo app, comment, delete. */
    statusOf(id) { return STATUSES.find((s) => s.id === id) || NEW_STATUS; },
    priorityTitle(id) { return PRIORITIES.find((p) => p.id === (id || 0))?.title || 'Не задан'; },
    priorityLabel(id) { return id ? `Приоритет: ${this.priorityTitle(id).toLowerCase()} (${id} из 5)` : 'Приоритет не задан'; },
    sortByPriority() { this.prioritySort = SORT_NEXT[this.prioritySort]; },
    get prioritySortTitle() {
      return { '': 'Сортировать по приоритету', desc: 'Сначала высокий приоритет', asc: 'Сначала низкий приоритет' }[this.prioritySort];
    },
    saveTint() { store.set(TINT_KEY, this.tintRows); },
    /* PATCH the lead; `instant` shows the change before the server answers and rolls it back on an error. */
    async saveCrm(patch, { done = '', instant = false } = {}) {
      const slug = this.selected;
      const before = this.crm;
      if (instant) this.crm = { ...before, ...patch };
      this.crmBusy = true;
      try {
        const { crm } = await api(this.itemUrl(encodeURIComponent(slug)), patch, 'PATCH');
        this.folderLeads = this.folderLeads.map((l) => (l.slug === slug ? { ...l, status: crm.status, priority: crm.priority } : l));
        if (this.selected === slug) this.crm = crm;
        if (done) this.notify(done);
        return true;
      } catch (e) {
        if (this.selected === slug) this.crm = before;
        if (e.status !== 401) this.notify(`Не сохранено: ${e.message}`);
        return false;
      } finally {
        this.crmBusy = false;
      }
    },
    setStatus(id) {
      const status = this.crm.status === id ? NEW_STATUS.id : id;  // a second click takes the status off
      this.saveCrm({ status }, { instant: true });
    },
    setPriority(id) { this.saveCrm({ priority: id }, { instant: true }); },
    isContacted(c) { return (this.crm?.contacted || []).some((x) => x.title === c.title && x.value === c.value); },
    toggleContacted(c) {
      const others = this.crm.contacted.filter((x) => !(x.title === c.title && x.value === c.value));
      const contacted = this.isContacted(c) ? others : [...others, { title: c.title, value: c.value }];
      this.saveCrm({ contacted }, { instant: true });
    },
    get commentChanged() { return this.crm && this.draft.comment.trim() !== this.crm.comment; },
    async saveComment() {
      if (await this.saveCrm({ comment: this.draft.comment }, { done: 'Комментарий сохранён' })) this.draft.comment = this.crm.comment;
    },
    get demoChanged() { return this.crm && this.draft.demoUrl.trim() !== (this.crm.demo_url || ''); },
    get demoUrlValid() { return !this.draft.demoUrl.trim() || /^https?:\/\/\S+$/i.test(this.draft.demoUrl.trim()); },
    async saveDemo() {
      const done = this.draft.demoUrl.trim() ? 'Ссылка на демо сохранена' : 'Ссылка на демо удалена';
      if (await this.saveCrm({ demo_url: this.draft.demoUrl }, { done })) this.draft.demoUrl = this.crm.demo_url || '';
    },
    async deleteLead() {
      const slug = this.selected;
      this.crmBusy = true;
      try {
        await api(this.itemUrl(encodeURIComponent(slug)), undefined, 'DELETE');
        this.folderLeads = this.folderLeads.filter((l) => l.slug !== slug);
        this.folders = this.folders.map((f) => (f.id === this.folderId ? { ...f, count: f.count - 1 } : f));
        this.picked = this.picked.filter((x) => x !== slug);
        this.closeCard();
        this.notify('Лид удалён');
      } catch (e) {
        this.deleteOpen = false;
        if (e.status !== 401) this.notify(`Не удалено: ${e.message}`);
      } finally {
        this.crmBusy = false;
      }
    },

    get cardName() { return this.card ? (this.card.row['Баня'] || this.card.row['Название']) : ''; },
    get cardPrices() {
      return this.card ? (this.card.lead.halls_from_2gis || this.card.lead.services_from_2gis || []) : [];
    },
    get heroStyle() {
      if (!this.card) return '';
      const accent = this.card.business.theme?.accent || '#5b5bd6';
      const img = this.card.business.theme?.hero ? `url(${this.itemUrl(this.selected)}/hero), ` : '';
      return `background-image: linear-gradient(180deg, transparent 35%, rgba(0,0,0,.72)), ${img}linear-gradient(135deg, ${accent}, #1d1d24)`;
    },
    /* Every contact of the 2GIS card with its label, the owner's first (card.contacts). Cards saved before
       labels existed only have the exported contacts: they are shown without labels. */
    get cardContacts() {
      if (!this.card) return [];
      if (this.card.contacts) return this.card.contacts;
      const c = this.card.lead.contact || {};
      const rows = [];
      if (c.whatsapp) rows.push(['WhatsApp', c.whatsapp]);
      if (c.telegram) rows.push(['Telegram', c.telegram]);
      if (this.card.row['Канал'] === 'ВКонтакте') rows.push(['ВКонтакте', this.card.row['Писать сюда']]);
      for (const p of c.phones || []) rows.push(['Телефон', p]);
      if (c.email) rows.push(['Email', c.email]);
      const site = c.website || this.card.business.contacts?.website;
      if (site) rows.push(['Сайт', site]);
      return rows.map(([title, value]) => ({
        title, value, href: this.contactHref(title, value), label: '', label_source: 'none', role: 'general' }));
    },
    get cardLegal() {
      if (!this.card) return { name: '', owner: null };
      return this.card.legal || { name: this.card.row['Юрлицо'] || '', owner: null };
    },
    labelHint(contact) {
      return {
        '2gis': 'Подпись из карточки 2ГИС',
        phone: 'В 2ГИС так подписан телефон с тем же номером',
        default: 'В 2ГИС подписи нет — подпись по умолчанию',
      }[contact.label_source] || '';
    },
    get writeHref() { return this.card ? this.contactHref('', this.card.row['Писать сюда']) : '#'; },
    /* The card's main action names its channel: «Написать в WhatsApp», «Позвонить». */
    get writeKind() { return this.card ? this.channelKind(this.card.row['Канал']) : 'phone'; },
    get writeLabel() {
      return { wa: 'Написать в WhatsApp', tg: 'Написать в Telegram', vk: 'Написать во ВКонтакте' }[this.writeKind] || 'Позвонить';
    },
    contactHref(kind, value) {
      if (/^https?:\/\//.test(value)) return value;
      if (kind === 'Email' || value.includes('@')) return `mailto:${value}`;
      return `tel:${value.replace(/[^\d+]/g, '')}`;
    },

    channelKind(channel = '') {
      if (channel.startsWith('WhatsApp')) return 'wa';
      if (channel.startsWith('Telegram')) return 'tg';
      if (channel.startsWith('ВКонтакте')) return 'vk';
      return 'phone';
    },
    channelLabel(channel = '') {
      return { wa: 'WhatsApp', tg: 'Telegram', vk: 'ВКонтакте' }[this.channelKind(channel)]
        || (channel.includes('мобильный') ? 'Звонок · моб.' : 'Звонок · гор.');
    },
    pricesShort(prices = []) {
      if (!prices.length) return '—';
      const head = prices.slice(0, 2).join(', ');
      return prices.length > 2 ? `${head} +${prices.length - 2}` : head;
    },
    initials(name = '') {
      return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase();
    },

    async copy(text, done) {
      try {
        await navigator.clipboard.writeText(text);
        this.notify(done);
      } catch {
        this.notify('Не удалось скопировать — выделите текст вручную');
      }
    },
    notify(text) {
      this.toast = text;
      clearTimeout(this._toastTimer);
      this._toastTimer = setTimeout(() => { this.toast = ''; }, TOAST_MS);
    },

    async pickFolder() {
      try {
        const { path } = await api('/api/leads/pick-folder', {});
        if (path) this.exportPath = path;
      } catch (e) {
        this.notify(e.message);
      }
    },
    async exportAll() {
      this.exporting = true;
      try {
        const body = { path: this.exportPath };
        if (this.picked.length) body.slugs = this.picked;
        const r = await api(this.onLeads ? `/api/folders/${this.folderId}/export` : '/api/leads/export', body);
        store.set(PATH_KEY, this.exportPath);
        this.saveSettings();
        this.exportOpen = false;
        this.notify(`Выгружено в ${r.path}: новых ${r.added}, обновлено ${r.updated}`);
      } catch (e) {
        this.notify(e.message);
      } finally {
        this.exporting = false;
      }
    },
    async openFolder() {
      await api('/api/leads/open-folder', { path: this.exportPath }).catch((e) => this.notify(e.message));
    },
  }));
});
