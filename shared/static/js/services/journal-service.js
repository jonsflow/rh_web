/**
 * Journal API client.
 *
 * Entries belong to a day, and optionally to one asset, one account and one
 * trade. The asset and account come from the current selection unless a caller
 * names them, so a note written on the futures dashboard is filed against
 * futures without the caller saying so.
 */
class JournalService {
    constructor(options = {}) {
        this.baseUrl = '';
        this._config = options.config || null;
    }

    get config() {
        return this._config || window.AssetConfig;
    }

    /** The asset and account an entry is filed against. */
    context({ assetType, account } = {}) {
        const config = this.config;
        return {
            asset_type: assetType !== undefined ? assetType : config.assetType,
            account_number: account !== undefined ? account : config.account
        };
    }

    /** @private */
    async _request(url, init = undefined) {
        const response = await fetch(url, init);
        const data = await response.json();

        if (!response.ok || data.error) {
            throw new Error(data.error || `HTTP error! status: ${response.status}`);
        }
        return data;
    }

    /** @private */
    _url(path, params = {}) {
        const search = new URLSearchParams();
        Object.keys(params).forEach(key => {
            const value = params[key];
            if (value !== null && value !== undefined && value !== '') {
                search.append(key, value);
            }
        });
        const query = search.toString();
        return `${this.baseUrl}${path}${query ? '?' + query : ''}`;
    }

    /**
     * Entries matching the filters given.
     * @param {Object} [filters] - date, start_date, end_date, type,
     *   reference_id, search; asset and account default to the selection
     * @returns {Promise<Array>}
     */
    async list(filters = {}) {
        const { asset_type, account_number } = this.context(filters);
        const data = await this._request(this._url('/api/journals', {
            date: filters.date,
            start_date: filters.start_date,
            end_date: filters.end_date,
            type: filters.type,
            reference_id: filters.reference_id,
            search: filters.search,
            asset_type: filters.allAssets ? null : asset_type,
            account: account_number
        }));
        return data.journals;
    }

    /**
     * Entry counts per date, for marking days in the calendar.
     * @returns {Promise<Object>} date -> count
     */
    async countsByDate(startDate, endDate, options = {}) {
        const { asset_type, account_number } = this.context(options);
        const data = await this._request(this._url('/api/journals/count-by-date', {
            start_date: startDate,
            end_date: endDate,
            asset_type: options.allAssets ? null : asset_type,
            account: account_number
        }));
        return data.counts;
    }

    /**
     * Write a new entry.
     * @param {Object} entry - journal_type, date, notes, and optionally tags
     *   and reference_id; asset and account default to the selection
     * @returns {Promise<Object>} the stored entry
     */
    async create(entry) {
        const { asset_type, account_number } = this.context(entry);
        const data = await this._request(this._url('/api/journals'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                journal_type: entry.journal_type || 'daily',
                date: entry.date,
                notes: entry.notes,
                tags: entry.tags || null,
                reference_id: entry.reference_id || null,
                asset_type,
                account_number
            })
        });
        return data.journal;
    }

    /**
     * Change an entry's notes, tags or date.
     * @returns {Promise<Object>} the stored entry
     */
    async update(journalId, updates) {
        const data = await this._request(this._url(`/api/journals/${journalId}`), {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updates)
        });
        return data.journal;
    }

    /** Remove an entry. */
    async remove(journalId) {
        await this._request(this._url(`/api/journals/${journalId}`), { method: 'DELETE' });
    }
}

window.JournalServiceClass = JournalService;
window.JournalService = new JournalService();
