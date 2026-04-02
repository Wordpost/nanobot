export const API = {
    async fetchSessions() {
        const res = await fetch('/api/sessions');
        if (!res.ok) throw new Error('Failed to fetch sessions');
        return await res.json();
    },

    async fetchSessionDetail(filename) {
        const res = await fetch(`/api/sessions/${filename}`);
        if (!res.ok) throw new Error('Failed to fetch session detail');
        return await res.json();
    },

    async fetchLogs() {
        const res = await fetch('/api/logs');
        if (!res.ok) throw new Error('Failed to fetch logs');
        return await res.json();
    },

    async fetchConfig() {
        const res = await fetch('/api/config');
        if (!res.ok) throw new Error('Failed to fetch config');
        return await res.json();
    },

    /**
     * Open SSE stream for Docker logs.
     * @returns {EventSource}
     */
    streamLogs(onLine, onError) {
        const es = new EventSource('/api/logs/stream');
        es.onmessage = (e) => {
            try {
                const data = JSON.parse(e.data);
                onLine(data.line, data.error);
            } catch {
                onLine(e.data);
            }
        };
        es.onerror = () => { if (onError) onError(); };
        return es;
    },

    /**
     * Open SSE stream for session list changes.
     * @returns {EventSource}
     */
    watchSessions(onUpdate, onError) {
        const es = new EventSource('/api/sessions/watch');
        es.onmessage = (e) => {
            try {
                const data = JSON.parse(e.data);
                onUpdate(data);
            } catch (err) {
                console.error('Session watch parse error:', err);
            }
        };
        es.onerror = () => { if (onError) onError(); };
        return es;
    }
};
