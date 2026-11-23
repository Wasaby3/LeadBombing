/* LeadBombing PWA: login, side menu pages (search, leads, clients, profile, settings, docs), search form, live leads
   table, saved lead folders («Сохранённые лиды»), clients («Клиенты»), lead card, export. Alpine.js + Motion.
   The work on a saved lead or client (statuses, priority, comment, demo, «Перевести в клиенты») is in crm.js,
   «Проработать лиды» (demo URLs of a folder's leads) in work.js, a folder's «Общее сообщение» in message.js. */
const POLL_MS = 900;
const SAVE_SETTINGS_MS = 800;
const TOAST_MS = 2600;
const FORM_KEY = 'lb.form';  // the form of the last search started: unsent edits are dropped when leaving the page
const PATH_KEY = 'lb.exportPath';
const THEME_KEY = 'lb.theme';
const TINT_KEY = 'lb.tintRows';  // table rows coloured by priority (on by default)
const PAGES = ['search', 'leads', 'clients', 'profile', 'settings', 'docs'];
const SORT_NEXT = { '': 'desc', desc: 'asc', asc: '' };  // priority column: high first, low first, folder order
/* Channel column: each click puts the next channel first (channelKind), the last one returns folder order. */
const CHANNEL_SORTS = ['', 'tg', 'wa', 'vk', 'phone'];
const CHANNEL_FIRST = { tg: 'Telegram', wa: 'WhatsApp', vk: 'ВКонтакте', phone: 'звонки' };
const OWNER_RANK = { owner: 2, maybe: 1 };  // row.owner from leads/contacts.py owner_mark
const OWNER_TITLES = { owner: 'Есть контакт руководителя', maybe: 'Возможно, номер владельца' };
/* Lead card sections, top to bottom; «Работа с клиентом» holds the sub-sections. All open when a lead is opened. */
const SECTIONS = ['contacts', 'prices', 'legal', 'work'];
const SUB_SECTIONS = ['channels', 'demo', 'message', 'hook', 'comment'];
const CUSTOM = { id: 'custom', title: 'Свободный поиск', query: '', fixed_city: null,
  note: 'Свободный поиск: все фирмы из выдачи 2ГИС по вашему запросу, выгрузка как у шаблонов' };
const STATUS_TEXT = { idle: 'Не запущен', running: 'Идёт поиск', done: 'Поиск завершён', stopped: 'Поиск остановлен',
  error: 'Поиск прерван' };
const NO_FORM_ERROR = { field: '', text: '' };

/* A guess, not a fact: the first unlabelled mobile phone is likely the owner's when the firm is an ИП or the card
   has no other phone. Skipped when 2GIS already names a director/owner contact. Adds likelyOwner (the reason). */
const isPhone = (c) => c.type ? c.type === 'phone' : c.title === 'Телефон'; // old cards have no type
const isMobilePhone = (c) => /^79\d{9}$/.test(c.value.replace(/\D/g, ''));
const isMessenger = (c) => ['whatsapp', 'telegram'].includes(c.type) || ['WhatsApp', 'Telegram'].includes(c.title);
/* A phone in international digits: 8XXXXXXXXXX → 7XXXXXXXXXX. */
const intlDigits = (value) => String(value || '').replace(/\D/g, '').replace(/^8(\d{10})$/, '7$1');
const MIN_PHONE_DIGITS = 10;
/* «Возможный контакт»: links that show whether a phone has Telegram or WhatsApp. */
const probeLinks = (digits) => [
  { title: 'Telegram', href: `https://t.me/+${digits}` },
  { title: 'WhatsApp', href: `https://wa.me/${digits}` },
];
function markLikelyOwner(contacts, isIp) {
  if (contacts.some((c) => c.role === 'owner')) return contacts;
  const phones = contacts.filter(isPhone);
  const reason = isIp ? 'мобильный · юрлицо ИП' : phones.length === 1 ? 'мобильный · единственный номер' : '';
  const pick = reason && phones.find((c) => isMobilePhone(c) && c.role === 'general');
  return pick ? contacts.map((c) => (c === pick ? { ...c, likelyOwner: reason } : c)) : contacts;
}

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
  exportOpen: ['exportDialog', null], saveOpen: ['saveDialog', null], workOpen: ['workDialog', null],
  messageOpen: ['messageDialog', 'moreBtn'],
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

/* Merge parts of the component (crm.js) keeping their getters as getters. */
function withParts(base, ...parts) {
  return parts.reduce((all, part) => Object.defineProperties(all, Object.getOwnPropertyDescriptors(part)), base);
}

document.addEventListener('alpine:init', () => {
  Alpine.data('leadsApp', () => withParts({
    meta: { spheres: [], cities: [] },
    form: loadForm(),
    searchForm: loadForm(),  // what the table was searched with; `form` returns to it unless «Найти лиды» is pressed
    citiesOpen: false, cityFilter: '', picked: [], moreOpen: false, formError: NO_FORM_ERROR,
    status: 'idle', error: '', log: '', cursor: 0,
    params: null, resumable: false, busy: false, searchCleared: false, clearOpen: false, _hadForm: false,
    leads: [], skipped: [], filter: '', showSkipped: false,
    selected: null, card: null, cardFolder: null,  // the folder of the open saved lead or client
    probeOpen: {},  // «Возможный контакт» opened per phone digits in the card
    exportOpen: false, exporting: false, exportPath: store.get(PATH_KEY, ''),
    toast: '', _toastTimer: null, _pollTimer: null,
    user: null, authChecked: false, auth: { login: '', password: '', error: '', busy: false },
    fromAccount: false, _settingsReady: false, _saveTimer: null,
    page: pageFromPath(), theme: store.get(THEME_KEY, ''), systemDark: DARK_QUERY.matches, themeChoices: THEME_CHOICES,
    folders: [], folderId: null, folderLeads: [],
    tintRows: store.get(TINT_KEY, true),
    saveOpen: false, saving: false, saveForm: { mode: 'new', name: '', folderId: null },
    prioritySort: '', ownerSort: false, channelSort: '', collapsed: {},
    folderWorkedOutside: 0,  // «Написали» of the folder not in its list: clients and deleted leads with a status

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
      // The network can drop a single request (VPN): retry before giving up, or the form is left without cities.
      for (let attempt = 1; ; attempt++) {
        try {
          this.meta = await api('/api/leads/meta');
          break;
        } catch (e) {
          if (attempt === 3) {
            this.error = 'Сервер не отвечает. Запустите leadbombing и обновите страницу.';
            return;
          }
          await new Promise((resolve) => setTimeout(resolve, 1000));
        }
      }
      await this.loadSettings();
      if (!this.sphere) this.form.sphere = 'bani';
      if (!this._hadForm && !this.form.query) this.form.query = this.sphere.query;  // first visit only
      this.searchForm = cloneForm(this.form);
      await this.poll();  // restore the current run after a reload
      if (!this.leads.length && !this.running && !this.searchCleared) await this.loadSaved();
      if (this.onLeads) await this.loadFolders();
      if (this.onClients) await this.loadClients();
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
      this.ownerSort = false;
      this.channelSort = '';
      this.closeCard();
      if (page === 'leads') this.loadFolders();
      if (page === 'clients') this.loadClients();
    },
    get onSearch() { return this.page === 'search'; },
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
    },
    async showFolder(id) {
      this.folderId = id;
      this.picked = [];
      this.closeCard();
      try {
        const r = await api(`/api/folders/${id}`);
        this.folderLeads = r.leads;
        this.folderWorkedOutside = r.worked_outside || 0;
      } catch (e) {
        this.folderLeads = [];
        this.folderWorkedOutside = 0;
        if (e.status !== 401) this.notify(`Папка не загружена: ${e.message}`);
      }
    },
    get folder() { return this.folders.find((f) => f.id === this.folderId); },

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
    /* A lead of the search, or a saved lead or client of the folder (the open card's by default). */
    itemUrl(slug, folderId = this.cardFolder) {
      return this.onSaved ? `/api/folders/${folderId}/item/${slug}` : `/api/leads/item/${slug}`;
    },
    rowUrl(l) { return this.itemUrl(l.slug, l.folder_id ?? this.folderId); },
    /* Client rows come from all folders: the same firm can be a client in two of them. */
    rowKey(l) { return l.folder_id ? `${l.folder_id}/${l.slug}` : l.slug; },
    isActive(l) { return this.selected === l.slug && (!this.onSaved || this.isRow(l, l.slug, this.cardFolder)); },
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
    get list() { return this.onLeads ? this.folderLeads : this.onClients ? this.clients : this.leads; },
    get exportCount() { return this.picked.length || this.list.length; },
    /* Export: a saved folder with leads, or a new search (leads of past searches come back only for viewing). */
    get canExport() {
      if (this.onSearch) return this.leads.length > 0 && !this.fromAccount;
      return this.onLeads && this.folderLeads.length > 0;
    },
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
      if (!this.prioritySort && !this.ownerSort && !this.channelSort) return found;
      const sign = this.prioritySort === 'desc' ? -1 : 1;
      const first = (l) => (this.channelKind(l.channel) === this.channelSort ? 0 : 1);
      const byChannel = (a, b) => (this.channelSort ? first(a) - first(b) : 0);
      const byPriority = (a, b) => (this.prioritySort ? sign * ((a.priority || 0) - (b.priority || 0)) : 0);
      const byOwner = (a, b) => (this.ownerSort ? (OWNER_RANK[b.owner] || 0) - (OWNER_RANK[a.owner] || 0) : 0);
      return [...found].sort((a, b) => byChannel(a, b) || byPriority(a, b) || byOwner(a, b));  // stable: ties keep folder order
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

    async openCard(slug, folderId = this.folderId) {
      this.selected = slug;
      this.cardFolder = this.onSaved ? folderId : null;
      this.card = null;
      this.collapsed = {};
      this.probeOpen = {};
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

    /* Table: priority sort, owner crowns, row tint. */
    sortByPriority() { this.prioritySort = SORT_NEXT[this.prioritySort]; },
    get nextChannelSort() { return CHANNEL_SORTS[(CHANNEL_SORTS.indexOf(this.channelSort) + 1) % CHANNEL_SORTS.length]; },
    sortByChannel() { this.channelSort = this.nextChannelSort; },
    get channelSortTitle() {
      return this.nextChannelSort ? `Сначала ${CHANNEL_FIRST[this.nextChannelSort]}` : 'Вернуть порядок папки';
    },
    get channelSortLabel() { return CHANNEL_FIRST[this.channelSort] || ''; },
    /* «Написали»: leads of the folder with a status other than «Ещё не написал», also those no longer in the list. */
    get workedCount() {
      return this.folderLeads.filter((l) => l.status && l.status !== 'not_written').length + this.folderWorkedOutside;
    },
    ownerTitle(mark) { return OWNER_TITLES[mark] || ''; },
    get prioritySortTitle() {
      return { '': 'Сортировать по приоритету', desc: 'Сначала высокий приоритет', asc: 'Сначала низкий приоритет' }[this.prioritySort];
    },
    saveTint() { store.set(TINT_KEY, this.tintRows); },

    /* A saved lead has its folder's «Общее сообщение» or the bathhouse one (card.demo_message) with its own demo link;
       otherwise the search's message. */
    get cardMessage() {
      if (!this.card) return '';
      if (!this.card.demo_message) return this.card.row['Сообщение'];
      return this.card.demo_message.replace('[ссылка на демо]', this.crm?.demo_url || '[ссылка на демо]');
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
      return markLikelyOwner(this.card.contacts || this.oldCardContacts(), !!this.cardLegal.owner);
    },
    oldCardContacts() {
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
    /* «Написать (возможно) руководителю»: the crowned contact; its WhatsApp/Telegram link, or wa.me/<phone digits>. */
    get ownerWrite() {
      const c = this.cardContacts.find((x) => x.role === 'owner') || this.cardContacts.find((x) => x.likelyOwner);
      if (!c) return null;
      const link = [c.href, c.value].find((v) => /^https?:\/\/(wa\.me|api\.whatsapp|t\.me|telegram)/.test(v || ''));
      const digits = intlDigits(c.value);
      const href = link || (digits ? `https://wa.me/${digits}` : '');
      if (!href) return null;
      return { href, label: c.role === 'owner' ? 'Написать руководителю' : 'Написать возможно руководителю' };
    },
    /* Digits of a phone that has no WhatsApp/Telegram of the same number in the card, else '' (no «Возможный контакт»). */
    probeDigits(contact) {
      if (!isPhone(contact)) return '';
      const digits = intlDigits(contact.value);
      if (digits.length < MIN_PHONE_DIGITS) return '';
      return this.cardContacts.some((c) => isMessenger(c) && intlDigits(c.value) === digits) ? '' : digits;
    },
    /* The number of «Позвонить» when the card's channel is a call. */
    get writeProbeDigits() {
      if (!this.card || this.writeKind !== 'phone') return '';
      return this.probeDigits({ type: 'phone', value: this.card.row['Писать сюда'] || '' });
    },
    toggleProbe(digits) { this.probeOpen = { ...this.probeOpen, [digits]: !this.probeOpen[digits] }; },
    probeLinks,
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
  }, crmPart(), workPart(), messagePart()));
});
