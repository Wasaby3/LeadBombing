/* «Общее сообщение» on «Сохранённые лиды»: one message for every lead card of the folder. The place of the lead's own
   demo link is marked by DEMO_MARK; each card puts its demo URL there (cardMessage in app.js). Saved in
   folders.message_template (web/folders_api.py, PUT /api/folders/<id>/message), never exported. An empty text brings
   back the sphere's message. Part of the leadsApp component (merged in app.js by withParts). */

const DEMO_MARK = '[ссылка на демо]';  // leads/spheres.py NO_DEMO_URL
const MAX_MESSAGE = 5000;  // web/lead_crm.py MAX_MESSAGE

function messagePart() {
  return {
    messageOpen: false, savingMessage: false, messageForm: { text: '', error: '' },

    /* Opens with the folder's message, else the open card's one (the sphere's default) to start from. */
    openMessage() {
      const fromCard = this.card && this.cardFolder === this.folderId ? this.card.demo_message : '';
      this.messageForm = { text: this.folder?.message_template || fromCard || '', error: '' };
      this.messageOpen = true;
    },
    /* Puts the demo link mark where the cursor is (or in place of the selection), the cursor after it. The field
       itself is edited, so the browser keeps the cursor and undo; the input event syncs x-model. */
    insertDemoMark() {
      const field = this.$refs.messageField;
      if (!field) return;
      field.focus();
      field.setRangeText(DEMO_MARK, field.selectionStart, field.selectionEnd, 'end');
      field.dispatchEvent(new Event('input', { bubbles: true }));
    },
    messageError(text) {
      if (text.length > MAX_MESSAGE) return `Сообщение длиннее ${MAX_MESSAGE} символов`;
      return '';
    },
    async saveMessage(reset = false) {
      const text = reset ? '' : this.messageForm.text.trim();
      const error = this.messageError(text);
      if (error) {
        this.messageForm = { ...this.messageForm, error };
        this.$refs.messageField?.focus();
        return;
      }
      this.savingMessage = true;
      try {
        const r = await api(`/api/folders/${this.folderId}/message`, { text }, 'PUT');
        this.folders = this.folders.map((f) => (f.id === this.folderId ? { ...f, message_template: r.message_template } : f));
        this.messageOpen = false;
        this.notify(r.message_template ? 'Общее сообщение сохранено' : 'Вернули стандартное сообщение');
        gnomeHears('message');
        if (this.selected && this.cardFolder === this.folderId) await this.openCard(this.selected);
      } catch (e) {
        if (e.status !== 401) this.messageForm = { ...this.messageForm, error: e.message };
      } finally {
        this.savingMessage = false;
      }
    },
  };
}
