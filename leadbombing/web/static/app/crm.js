/* Work on a saved lead («Сохранённые лиды») and on a client («Клиенты»): statuses, priority, contacted channels,
   demo app, comment, «Перевести в клиенты», delete. Part of the leadsApp component (merged in app.js by withParts);
   `this` is the component, `api`, `plural` and `notify` come from app.js. */

/* Lead statuses in the order of the picker; a lead new to a folder has not been written to yet. */
const STATUSES = [
  { id: 'not_written', title: 'Ещё не написал' }, { id: 'written', title: 'Написал' },
  { id: 'in_progress', title: 'В работе' }, { id: 'almost', title: 'Почти купил' },
  { id: 'bought', title: 'Купил' }, { id: 'refused', title: 'Отказался' },
];
/* Client statuses on «Клиенты»: a lead made a client starts with «Всё ок». */
const CLIENT_STATUSES = [
  { id: 'ok', title: 'Всё ок' }, { id: 'question', title: 'Есть вопрос' }, { id: 'bug', title: 'Срочный баг' },
];
const CLIENT_WORDS = ['клиент', 'клиента', 'клиентов'];
/* Lead priority 0–5: set by hand, or assessed from the 2GIS card (leads/booking.py); 5 is the hottest. */
const PRIORITIES = [{ id: 5, short: '5', title: 'Очень высокий', icon: 'flame-high' },
  { id: 4, short: '4', title: 'Высокий', icon: 'flame' }, { id: 3, short: '3', title: 'Средний', icon: 'sun' },
  { id: 2, short: '2', title: 'Низкий', icon: 'cloud' }, { id: 1, short: '1', title: 'Очень низкий', icon: 'snowflake' },
  { id: 0, short: 'Нет', title: 'Не задан', icon: 'circle-dashed' }];

function crmPart() {
  return {
    statuses: STATUSES, clientStatuses: CLIENT_STATUSES, priorities: PRIORITIES,
    crm: null, draft: { comment: '', demoUrl: '' }, crmBusy: false, deleteOpen: false,
    clients: [], movingToClients: false,

    get onClients() { return this.page === 'clients'; },
    /* A saved lead or a client: the card has the work on it. */
    get onSaved() { return this.onLeads || this.onClients; },
    get isClient() { return !!this.crm?.client_status; },
    clientsWord(n) { return plural(n, CLIENT_WORDS); },
    statusOf(id) { return STATUSES.find((s) => s.id === id) || STATUSES[0]; },
    clientStatusOf(id) { return CLIENT_STATUSES.find((s) => s.id === id) || CLIENT_STATUSES[0]; },
    priorityTitle(id) { return PRIORITIES.find((p) => p.id === (id || 0))?.title || 'Не задан'; },
    priorityIcon(id) { return `/static/app/vendor/icons.svg#${PRIORITIES.find((p) => p.id === (id || 0))?.icon || 'circle-dashed'}`; },
    priorityLabel(id) { return id ? `Приоритет: ${this.priorityTitle(id).toLowerCase()} (${id} из 5)` : 'Приоритет не задан'; },

    async loadClients() {
      try {
        this.clients = (await api('/api/clients')).clients;
      } catch (e) {
        this.clients = [];
        if (e.status !== 401) this.notify(`Клиенты не загружены: ${e.message}`);
      }
    },
    /* Is `l` the row of this lead? Client rows carry their folder, folder rows are of the shown folder. */
    isRow(l, slug, folderId) { return l.slug === slug && (l.folder_id ?? this.folderId) === folderId; },
    /* The row of the open card in the current table gets the new statuses and priority. */
    updateRow(slug, folderId, crm) {
      const fields = { status: crm.status, priority: crm.priority, client_status: crm.client_status };
      const patch = (l) => (this.isRow(l, slug, folderId) ? { ...l, ...fields } : l);
      if (this.onClients) this.clients = this.clients.map(patch);
      else this.folderLeads = this.folderLeads.map(patch);
    },
    /* The open card's row leaves the table: deleted, or a lead made a client. */
    dropRow(slug, folderId) {
      const other = (l) => !this.isRow(l, slug, folderId);
      if (this.onClients) {
        this.clients = this.clients.filter(other);
      } else {
        this.folderLeads = this.folderLeads.filter(other);
        this.folders = this.folders.map((f) => (f.id === folderId ? { ...f, count: f.count - 1 } : f));
        this.picked = this.picked.filter((x) => x !== slug);
      }
      if (this.isRow({ slug: this.selected, folder_id: this.cardFolder }, slug, folderId)) this.closeCard();
    },

    /* PATCH the lead; `instant` shows the change before the server answers and rolls it back on an error. */
    async saveCrm(patch, { done = '', instant = false } = {}) {
      const slug = this.selected;
      const folderId = this.cardFolder;
      const before = this.crm;
      if (instant) this.crm = { ...before, ...patch };
      this.crmBusy = true;
      try {
        const { crm } = await api(this.itemUrl(encodeURIComponent(slug)), patch, 'PATCH');
        this.updateRow(slug, folderId, crm);
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
    setStatus(id) { if (this.crm.status !== id) this.saveCrm({ status: id }, { instant: true }); },
    setClientStatus(id) { if (this.crm.client_status !== id) this.saveCrm({ client_status: id }, { instant: true }); },
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

    /* «Перевести в клиенты»: the lead becomes a client («Купил», «Всё ок») and moves to «Клиенты». */
    async makeClient() {
      const slug = this.selected;
      const folderId = this.cardFolder;  // another card may be opened while the request runs
      const name = this.cardName;
      this.crmBusy = true;
      this.movingToClients = true;
      try {
        await api(`${this.itemUrl(encodeURIComponent(slug))}/client`, {});
        this.dropRow(slug, folderId);
        this.notify(`«${name}» — теперь клиент`);
      } catch (e) {
        if (e.status !== 401) this.notify(`Не переведено в клиенты: ${e.message}`);
      } finally {
        this.crmBusy = false;
        this.movingToClients = false;
      }
    },
    get deleteLabel() { return this.isClient ? 'Удалить клиента' : 'Удалить лид'; },
    async deleteLead() {
      const slug = this.selected;
      const folderId = this.cardFolder;
      const done = this.isClient ? 'Клиент удалён' : 'Лид удалён';
      this.crmBusy = true;
      try {
        await api(this.itemUrl(encodeURIComponent(slug)), undefined, 'DELETE');
        this.dropRow(slug, folderId);
        this.notify(done);
      } catch (e) {
        this.deleteOpen = false;
        if (e.status !== 401) this.notify(`Не удалено: ${e.message}`);
      } finally {
        this.crmBusy = false;
      }
    },
  };
}
