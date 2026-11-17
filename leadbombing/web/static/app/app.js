/* LeadBombing PWA: login, side menu pages (search, saved, profile, settings, docs), search form, live leads table,
   saved lead folders, lead card, export. Alpine.js + Motion. */
const POLL_MS = 900;
const SAVE_SETTINGS_MS = 800;
const TOAST_MS = 2600;
const FORM_KEY = 'lb.form';
const PATH_KEY = 'lb.exportPath';
const THEME_KEY = 'lb.theme';
const PAGES = ['search', 'saved', 'profile', 'settings', 'docs'];
const CUSTOM = { id: 'custom', title: 'Свободный поиск', query: '', fixed_city: null,
  note: 'Свободный поиск: все фирмы из выдачи 2ГИС по вашему запросу, выгрузка как у шаблонов' };

function loadForm(saved = store.get(FORM_KEY, {})) {
  const form = { sphere: 'bani', query: '', cities: ['moscow'], limit: 100, showChrome: false, ...saved };
  if (!Array.isArray(form.cities) || !form.cities.length) form.cities = [saved.city || 'moscow'];
  delete form.city;
  return form;
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

function applyTheme(theme) {
  if (theme) document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
}
applyTheme(store.get(THEME_KEY, ''));  // before first paint: no flash of the wrong theme

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  };
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
    citiesOpen: false, cityFilter: '', picked: [],
    status: 'idle', error: '', log: '', cursor: 0,
    leads: [], skipped: [], filter: '', showSkipped: false,
    selected: null, card: null,
    exportOpen: false, exporting: false, exportPath: store.get(PATH_KEY, ''),
    toast: '', _toastTimer: null, _pollTimer: null,
    user: null, authChecked: false, auth: { login: '', password: '', error: '', busy: false },
    fromAccount: false, _settingsReady: false, _saveTimer: null,
    page: pageFromPath(), theme: store.get(THEME_KEY, ''),
    folders: [], folderId: null, folderLeads: [],
    saveOpen: false, saving: false, saveForm: { mode: 'new', name: '', folderId: null },

    async init() {
      this.$watch('citiesOpen', (open) => open && this.$nextTick(() => this.$refs.cityFilter.focus()));
      this.$watch('form', (f) => { store.set(FORM_KEY, f); this.saveSettings(); }, { deep: true });
      this.$watch('exportPath', () => this.saveSettings());
      window.addEventListener('popstate', () => this.showPage(pageFromPath()));
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
      if (!this.form.query) this.form.query = this.sphere.query;
      await this.poll();  // restore the current run after a reload
      if (!this.leads.length && !this.running) await this.loadSaved();
      if (this.onSaved) await this.loadFolders();
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
      this.page = page;
      this.picked = [];
      this.filter = '';
      this.closeCard();
      if (page === 'saved') this.loadFolders();
    },
    get onSaved() { return this.page === 'saved'; },

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
        this.folderLeads = (await api(`/api/folders/${id}`)).leads;
      } catch (e) {
        this.folderLeads = [];
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
        this.notify(`Сохранено ${r.saved} в папку «${r.folder.name}»`);
      } catch (e) {
        this.notify(e.message);
      } finally {
        this.saving = false;
      }
    },
    itemUrl(slug) {
      return this.onSaved ? `/api/folders/${this.folderId}/item/${slug}` : `/api/leads/item/${slug}`;
    },
    get currentTheme() {
      return this.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    },
    setTheme(theme) {
      this.theme = theme;
      store.set(THEME_KEY, theme);
      applyTheme(theme);
    },
    get initial() { return (this.user || '?').slice(0, 1).toUpperCase(); },

    async loadSettings() {
      this._settingsReady = false;
      try {
        const { settings } = await api('/api/account/settings');
        if (settings.form) this.form = loadForm(settings.form);
        if (settings.exportPath) this.exportPath = settings.exportPath;
      } catch (e) {
        if (e.status !== 401) this.notify(`Настройки не загружены: ${e.message}`);
      }
      await this.$nextTick();
      this._settingsReady = true;
    },
    saveSettings() {
      if (!this._settingsReady || !this.user) return;
      clearTimeout(this._saveTimer);
      this._saveTimer = setTimeout(() => {
        api('/api/account/settings', { settings: { form: this.form, exportPath: this.exportPath } })
          .catch((e) => { if (e.status !== 401) this.notify(`Настройки не сохранены: ${e.message}`); });
      }, SAVE_SETTINGS_MS);
    },
    async loadSaved() {
      try {
        const { leads } = await api('/api/account/leads');
        this.leads = leads.map((l) => ({ ...l, has_photo: false }));  // photos stay in the run folder
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
    get list() { return this.onSaved ? this.folderLeads : this.leads; },
    get exportCount() { return this.picked.length || this.list.length; },
    get allVisiblePicked() {
      return this.visible.length > 0 && this.visible.every((l) => this.picked.includes(l.slug));
    },
    get running() { return this.status === 'running'; },
    get isBani() { return (this.onSaved ? this.folder?.sphere : this.form.sphere) === 'bani'; },
    get pricesTitle() { return this.isBani ? 'Залы' : 'Услуги'; },
    get statusText() {
      return { idle: 'Готов', running: 'Идёт поиск', done: 'Готово', stopped: 'Остановлено', error: 'Ошибка' }[this.status];
    },
    get visible() {
      const q = this.filter.trim().toLowerCase();
      if (!q) return this.list;
      return this.list.filter((l) => `${l.name} ${l.district}`.toLowerCase().includes(q));
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

    async start() {
      this.error = '';
      this.citiesOpen = false;
      if (this.form.sphere === CUSTOM.id && !this.form.query.trim()) {
        this.error = 'Введите, что искать, или выберите сферу из списка';
        return;
      }
      if (!this.searchCities.length) {
        this.error = 'Выберите хотя бы один регион';
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
      this.schedulePoll();
    },

    async stop() {
      await api('/api/leads/stop', {}).catch((e) => { this.error = e.message; });
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
      this.log = (s.log || '').replace(/^\d\d:\d\d:\d\d\s*/, '');
      if (s.error) this.error = s.error;
      if (this.running) this.schedulePoll();
      else if (s.status === 'done' && s.events.length) this.notify(`Поиск завершён: ${this.leads.length} лидов`);
    },

    appear(el) {
      if (window.Motion) Motion.animate(el, { opacity: [0, 1], transform: ['translateY(6px)', 'none'] }, { duration: 0.35 });
    },

    async openCard(slug) {
      this.selected = slug;
      this.card = null;
      try {
        this.card = await api(this.itemUrl(encodeURIComponent(slug)));
      } catch (e) {
        this.closeCard();
        this.notify(e.message);
      }
    },
    closeCard() { this.selected = null; this.card = null; },

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
        const r = await api(this.onSaved ? `/api/folders/${this.folderId}/export` : '/api/leads/export', body);
        store.set(PATH_KEY, this.exportPath);
        this.saveSettings();
        this.exportOpen = false;
        this.notify(`Выгружено: добавлено ${r.added}, обновлено ${r.updated} → ${r.path}`);
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
