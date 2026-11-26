/* Lead statuses (Настройки → «Статусы лидов»): own name and color for each, up to MAX_STATUSES. Renaming or
   recoloring a status shows everywhere at once — a lead only stores its status id, this list supplies the
   name/color (statusOf, used by crm.js's picker and the leads table in index.html). The default status isn't a
   field of its own — it's always statuses[0] (the smallest sort_order). Deleting one moves its leads to whatever
   becomes statuses[0] once it's gone; «Ещё не написал» and «Купил» can be renamed and recolored but not deleted
   (web/lead_statuses.py). In Настройки a status looks exactly like its picker pill (crm.js's .st-btn) — the only
   difference is its name can be clicked into edit and its dot opens the color popup. Part of the leadsApp
   component (merged in app.js by withParts). */

const MAX_STATUSES = 9;
const STATUS_PALETTE = [
  { id: 'neutral', title: 'Серый' }, { id: 'good', title: 'Зелёный' }, { id: 'wait', title: 'Жёлтый' },
  { id: 'active', title: 'Синий' }, { id: 'warm', title: 'Оранжевый' }, { id: 'bad', title: 'Красный' },
  { id: 'purple', title: 'Фиолетовый' }, { id: 'teal', title: 'Бирюзовый' }, { id: 'pink', title: 'Розовый' },
];
const STATUS_COLOR_VARS = { neutral: '--muted', good: '--st-good', wait: '--st-wait', active: '--st-active',
  warm: '--st-warm', bad: '--st-bad', purple: '--st-purple', teal: '--st-teal', pink: '--st-pink' };
const PROTECTED_STATUSES = ['not_written', 'bought'];  // web/lead_statuses.py PROTECTED_IDS

function statusesPart() {
  return {
    statuses: [], statusPalette: STATUS_PALETTE, statusesBusy: false,
    statusColorOpenId: null, statusEditId: null, statusDeleteOpen: false, statusDeleteId: null,
    _statusNameBeforeEdit: '',

    statusColorVar(color) { return `var(${STATUS_COLOR_VARS[color] || STATUS_COLOR_VARS.neutral})`; },
    statusOf(id) { return this.statuses.find((s) => s.id === id) || this.statuses[0] || { id, name: '', color: 'neutral' }; },
    isProtectedStatus(id) { return PROTECTED_STATUSES.includes(id); },
    get canAddStatus() { return this.statuses.length < MAX_STATUSES; },

    async loadLeadStatuses() {
      try {
        this.statuses = (await api('/api/account/lead-statuses')).statuses;
      } catch (e) {
        if (e.status !== 401) this.notify(`Статусы не загружены: ${e.message}`);
      }
    },
    /* «Добавить статус» adds one named «Новый статус» right away, with a color not already used by another
       status — no dialog, nothing to fill in first. */
    async addStatus() {
      if (!this.canAddStatus) return;
      this.statusesBusy = true;
      try {
        const { status } = await api('/api/account/lead-statuses', {});
        this.statuses = [...this.statuses, status];
      } catch (e) {
        if (e.status !== 401) this.notify(`Не добавлено: ${e.message}`);
      } finally {
        this.statusesBusy = false;
      }
    },
    /* Clicking the name turns it into a text field; typing updates the pill at once, leaving it saves (or
       reverts, on an empty name or a rejected one). */
    startEditStatusName(s) {
      this.statusEditId = s.id;
      this._statusNameBeforeEdit = s.name;
    },
    onStatusNameInput(s, value) {
      this.statuses = this.statuses.map((x) => (x.id === s.id ? { ...x, name: value } : x));
    },
    async finishEditStatusName(s) {
      this.statusEditId = null;
      const before = this._statusNameBeforeEdit;
      const trimmed = s.name.trim();
      if (!trimmed || trimmed === before) {
        this.statuses = this.statuses.map((x) => (x.id === s.id ? { ...x, name: before } : x));
        return;
      }
      try {
        const { status } = await api(`/api/account/lead-statuses/${s.id}`, { name: trimmed }, 'PATCH');
        this.statuses = this.statuses.map((x) => (x.id === s.id ? status : x));
      } catch (e) {
        if (e.status !== 401) this.notify(`Название не сохранено: ${e.message}`);
        this.statuses = this.statuses.map((x) => (x.id === s.id ? { ...x, name: before } : x));
      }
    },
    /* Clicking the dot opens the (square) color popup; a second click on it, or picking a color, closes it. */
    toggleStatusColorPicker(id) {
      this.statusColorOpenId = this.statusColorOpenId === id ? null : id;
    },
    async recolorStatus(s, color) {
      this.statusColorOpenId = null;
      if (s.color === color) return;
      this.statuses = this.statuses.map((x) => (x.id === s.id ? { ...x, color } : x));
      try {
        const { status } = await api(`/api/account/lead-statuses/${s.id}`, { color }, 'PATCH');
        this.statuses = this.statuses.map((x) => (x.id === s.id ? status : x));
      } catch (e) {
        if (e.status !== 401) this.notify(`Цвет не сохранён: ${e.message}`);
      }
    },
    openDeleteStatus(id) {
      this.statusDeleteId = id;
      this.statusDeleteOpen = true;
    },
    async deleteStatus() {
      const id = this.statusDeleteId;
      this.statusesBusy = true;
      try {
        await api(`/api/account/lead-statuses/${id}`, undefined, 'DELETE');
        this.statuses = this.statuses.filter((x) => x.id !== id);
        this.statusDeleteOpen = false;
        this.notify('Статус удалён');
      } catch (e) {
        this.statusDeleteOpen = false;
        if (e.status !== 401) this.notify(`Не удалено: ${e.message}`);
      } finally {
        this.statusesBusy = false;
      }
    },
  };
}
