/**
 * Forensic State Management (ES Module)
 */
export const state = {
    sessions: [],
    filteredSessions: [],
    activeSession: null,
    logs: '',
    config: {},
    searchQuery: '',
    activeChannel: 'all',
    activeAgent: 'all',
    isLoading: false,

    listeners: [],

    subscribe(callback) {
        this.listeners.push(callback);
    },

    notify() {
        this.listeners.forEach(cb => cb(this));
    },

    async update(updates) {
        Object.assign(this, updates);
        this.notify();
    },

    setSearch(query) {
        this.searchQuery = query.toLowerCase();
        this.filter();
    },

    setChannel(channel) {
        this.activeChannel = channel;
        this.filter();
    },

    setAgent(agent) {
        this.activeAgent = agent;
        this.filter();
    },

    filter() {
        this.filteredSessions = this.sessions.filter(s => {
            const matchesSearch = s.key?.toLowerCase().includes(this.searchQuery) || 
                                  s.filename?.toLowerCase().includes(this.searchQuery);
            const matchesChannel = this.activeChannel === 'all' || s.channel === this.activeChannel;
            const matchesAgent = this.activeAgent === 'all' || s.agent === this.activeAgent;
            return matchesSearch && matchesChannel && matchesAgent;
        });
        this.notify();
    }
};
