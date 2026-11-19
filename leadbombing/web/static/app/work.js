/* «Проработать лиды» on «Сохранённые лиды»: the window with the demo app's base URL and the run over the folder's
   leads (all or the picked ones). Each lead gets the demo URL base + "/" + its slug, the same name as its
   tenants/<slug>/ folder in an export (web/work_api.py). Part of the leadsApp component (merged in app.js by
   withParts); `this` is the component, `api`, `notify`, `leadsWord` and `formatDate` come from app.js. */

/* A scheme and a host, no spaces, ? or #: the server checks the same (lead_crm.parse_base_url). */
const BASE_URL_RE = /^https?:\/\/[^/\s?#]+[^\s?#]*$/i;

function workPart() {
  return {
    workOpen: false, working: false, workForm: { baseUrl: '', error: '' },

    get workBase() { return this.workForm.baseUrl.trim().replace(/\/+$/, ''); },
    get workUrlValid() { return BASE_URL_RE.test(this.workBase); },
    /* What the first lead's link will look like, so the user sees where the slug goes. */
    get workExample() {
      const slug = this.picked[0] || this.folderLeads[0]?.slug;
      return this.workUrlValid && slug ? `${this.workBase}/${slug}` : '';
    },
    get workedBefore() { return this.folder?.demo_filled_at ? this.formatDate(this.folder.demo_filled_at) : ''; },

    openWork() {
      this.workForm = { baseUrl: this.folder?.demo_base_url || '', error: '' };
      this.workOpen = true;
    },
    async runWork() {
      if (!this.workUrlValid) {
        this.workForm.error = 'Адрес должен начинаться с http:// или https://, без пробелов, ? и #';
        return;
      }
      const body = { base_url: this.workBase };
      if (this.picked.length) body.slugs = this.picked;
      this.working = true;
      try {
        const r = await api(`/api/folders/${this.folderId}/work`, body);
        this.folders = this.folders.map((f) => (f.id === this.folderId
          ? { ...f, demo_base_url: r.base_url, demo_filled_at: r.filled_at } : f));
        this.workOpen = false;
        const kept = r.kept ? `, со своей ссылкой оставлено: ${r.kept}` : '';
        this.notify(`Ссылка на демо проставлена: ${r.filled} ${this.leadsWord(r.filled)}${kept}`);
        if (this.selected && this.cardFolder === this.folderId) await this.openCard(this.selected);
      } catch (e) {
        if (e.status !== 401) this.workForm.error = e.message;
      } finally {
        this.working = false;
      }
    },
  };
}
