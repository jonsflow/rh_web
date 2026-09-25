/**
 * Journal panel: the entries for a day or a trade, plus a box to add one.
 *
 * Rendered inside the calendar's day modal, below the day's tables. Writing a
 * note is the point, so the form is always open rather than behind a button.
 */

function journalEscape(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

/** A timestamp as the writer would read it. */
function writtenAt(value) {
    if (!value) return '';
    const when = new Date(value);
    return isNaN(when.getTime()) ? '' : when.toLocaleString();
}


class JournalPanel {
    /**
     * @param {Object} [options]
     * @param {Object} [options.service] - JournalService, for tests
     */
    constructor(options = {}) {
        this._service = options.service || null;
        this.entries = [];
        this.date = null;
        this.referenceId = null;
        this.journalType = 'daily';
        this.editingId = null;
    }

    get service() {
        return this._service || window.JournalService;
    }

    /**
     * Load the entries for a day, or for one trade on that day.
     * @param {string} date - YYYY-MM-DD
     * @param {Object} [options] - journalType and referenceId
     */
    async load(date, options = {}) {
        this.date = date;
        this.journalType = options.journalType || 'daily';
        this.referenceId = options.referenceId || null;
        this.editingId = null;

        try {
            this.entries = await this.service.list({
                date,
                reference_id: this.referenceId
            });
        } catch (error) {
            console.error('Failed to load journal entries:', error);
            this.entries = [];
        }
        return this.entries;
    }

    /** The panel's HTML for the entries currently loaded. */
    render() {
        return `
            <div class="journal-panel" data-journal-date="${journalEscape(this.date)}">
                <h3>Journal</h3>
                ${this.renderEntries()}
                ${this.renderForm()}
            </div>
        `;
    }

    renderEntries() {
        if (this.entries.length === 0) {
            return '<p class="journal-empty">No notes for this day yet.</p>';
        }

        const entries = this.entries.map(entry => {
            if (entry.id === this.editingId) return this.renderEditor(entry);

            const tags = (entry.tags || '')
                .split(',')
                .map(tag => tag.trim())
                .filter(Boolean)
                .map(tag => `<span class="journal-tag">${journalEscape(tag)}</span>`)
                .join('');

            return `
                <div class="journal-entry" data-journal-id="${entry.id}">
                    <div class="journal-entry-header">
                        <span class="journal-type">${journalEscape(entry.journal_type)}</span>
                        ${entry.asset_type ? `<span class="journal-asset">${journalEscape(entry.asset_type)}</span>` : ''}
                        ${tags}
                        <span class="journal-written">${journalEscape(writtenAt(entry.created_at))}</span>
                    </div>
                    <div class="journal-notes">${journalEscape(entry.notes)}</div>
                    <div class="journal-entry-actions">
                        <button type="button" class="btn-small journal-edit" data-journal-id="${entry.id}">Edit</button>
                        <button type="button" class="btn-small journal-delete" data-journal-id="${entry.id}">Delete</button>
                    </div>
                </div>
            `;
        }).join('');

        return `<div class="journal-entries">${entries}</div>`;
    }

    /** One entry swapped for its editing form. */
    renderEditor(entry) {
        return `
            <div class="journal-entry journal-entry-editing" data-journal-id="${entry.id}">
                <textarea class="journal-edit-notes" rows="3">${journalEscape(entry.notes)}</textarea>
                <input type="text" class="journal-edit-tags" value="${journalEscape(entry.tags || '')}"
                       placeholder="tags, comma separated">
                <div class="journal-entry-actions">
                    <button type="button" class="btn-small journal-save" data-journal-id="${entry.id}">Save</button>
                    <button type="button" class="btn-small journal-cancel">Cancel</button>
                </div>
            </div>
        `;
    }

    renderForm() {
        return `
            <div class="journal-form">
                <textarea id="journalNotes" rows="3" placeholder="What happened, and what you would do differently"></textarea>
                <input type="text" id="journalTags" placeholder="tags, comma separated">
                <button type="button" class="btn journal-add">Add note</button>
                <span class="journal-error" id="journalError"></span>
            </div>
        `;
    }

    /**
     * Put the panel in a container and wire its buttons.
     * @param {HTMLElement} container
     */
    mount(container) {
        if (!container) return;
        container.innerHTML = this.render();
        this._wire(container);
    }

    /** @private */
    _wire(container) {
        const redraw = () => this.mount(container);

        const add = container.querySelector('.journal-add');
        if (add) {
            add.addEventListener('click', async () => {
                const notes = container.querySelector('#journalNotes');
                const tags = container.querySelector('#journalTags');
                const error = container.querySelector('#journalError');

                if (!notes || !notes.value.trim()) {
                    if (error) error.textContent = 'Write something first.';
                    return;
                }

                try {
                    await this.service.create({
                        journal_type: this.journalType,
                        date: this.date,
                        notes: notes.value,
                        tags: tags ? tags.value : null,
                        reference_id: this.referenceId
                    });
                    await this.load(this.date, {
                        journalType: this.journalType,
                        referenceId: this.referenceId
                    });
                    redraw();
                } catch (failure) {
                    if (error) error.textContent = failure.message;
                }
            });
        }

        container.querySelectorAll('.journal-edit').forEach(button => {
            button.addEventListener('click', () => {
                this.editingId = Number(button.dataset.journalId);
                redraw();
            });
        });

        const cancel = container.querySelector('.journal-cancel');
        if (cancel) {
            cancel.addEventListener('click', () => {
                this.editingId = null;
                redraw();
            });
        }

        const save = container.querySelector('.journal-save');
        if (save) {
            save.addEventListener('click', async () => {
                const notes = container.querySelector('.journal-edit-notes');
                const tags = container.querySelector('.journal-edit-tags');

                try {
                    await this.service.update(Number(save.dataset.journalId), {
                        notes: notes ? notes.value : '',
                        tags: tags ? tags.value : null
                    });
                    this.editingId = null;
                    await this.load(this.date, {
                        journalType: this.journalType,
                        referenceId: this.referenceId
                    });
                    redraw();
                } catch (failure) {
                    console.error('Failed to save journal entry:', failure);
                }
            });
        }

        container.querySelectorAll('.journal-delete').forEach(button => {
            button.addEventListener('click', async () => {
                try {
                    await this.service.remove(Number(button.dataset.journalId));
                    await this.load(this.date, {
                        journalType: this.journalType,
                        referenceId: this.referenceId
                    });
                    redraw();
                } catch (failure) {
                    console.error('Failed to delete journal entry:', failure);
                }
            });
        });
    }
}

window.JournalPanel = JournalPanel;
