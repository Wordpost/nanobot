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

    async fetchLogs(agent) {
        const params = agent ? `?agent=${agent}` : '';
        const res = await fetch(`/api/logs${params}`);
        if (!res.ok) throw new Error('Failed to fetch logs');
        return await res.json();
    },

    async fetchConfig() {
        const res = await fetch('/api/config');
        if (!res.ok) throw new Error('Failed to fetch config');
        return await res.json();
    },

    async fetchConfigManager(agent) {
        const params = agent ? `?agent=${agent}` : '';
        const res = await fetch(`/api/config-manager${params}`);
        if (!res.ok) throw new Error('Failed to fetch full config.json');
        return await res.json();
    },

    async saveConfigManager(payload, agent) {
        const params = agent ? `?agent=${agent}` : '';
        const res = await fetch(`/api/config-manager${params}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) {
            const errString = await res.text();
            throw new Error(`Save failed: ${errString}`);
        }
        return await res.json();
    },

    /**
     * Open SSE stream for Docker logs.
     * @param {Function} onLine
     * @param {Function} onError
     * @param {string} [agent] - agent name for pool mode
     * @returns {EventSource}
     */
    streamLogs(onLine, onError, agent) {
        const params = agent ? `?agent=${agent}` : '';
        const es = new EventSource(`/api/logs/stream${params}`);
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
    },

    /**
     * Open SSE stream for System Deployment (all agents).
     * @returns {EventSource}
     */
    streamDeploy(onLine, onError) {
        const es = new EventSource('/api/system/deploy/stream');
        es.onmessage = (e) => {
            try {
                const data = JSON.parse(e.data);
                onLine(data.line, data.error, data.done);
                if (data.done) es.close();
            } catch {
                onLine(e.data);
            }
        };
        es.onerror = () => { if (onError) onError(); };
        return es;
    },

    /**
     * Open SSE stream for System Restart (specific agent).
     * @param {Function} onLine
     * @param {Function} onError
     * @param {string} [agent] - agent name for pool mode
     * @returns {EventSource}
     */
    streamRestart(onLine, onError, agent) {
        const params = agent ? `?agent=${agent}` : '';
        const es = new EventSource(`/api/system/restart/stream${params}`);
        es.onmessage = (e) => {
            try {
                const data = JSON.parse(e.data);
                onLine(data.line, data.error, data.done);
                if (data.done) es.close();
            } catch {
                onLine(e.data);
            }
        };
        es.onerror = () => { if (onError) onError(); };
        return es;
    },

    // ── Subagent API ──────────────────────────────────────────

    async fetchSubagents(agent) {
        const params = agent ? `?agent=${agent}` : '';
        const res = await fetch(`/api/subagents${params}`);
        if (!res.ok) throw new Error('Failed to fetch subagents');
        return await res.json();
    },

    async fetchSubagentDetail(filename) {
        const res = await fetch(`/api/subagents/${filename}`);
        if (!res.ok) throw new Error('Failed to fetch subagent detail');
        return await res.json();
    },

    watchSubagents(onUpdate, onError, agent) {
        const params = agent ? `?agent=${agent}` : '';
        const es = new EventSource(`/api/subagents/watch${params}`);
        es.onmessage = (e) => {
            try {
                const data = JSON.parse(e.data);
                onUpdate(data);
            } catch (err) {
                console.error('Subagent watch parse error:', err);
            }
        };
        es.onerror = () => { if (onError) onError(); };
        return es;
    },

    // ── Session Management ───────────────────────────────────

    async deleteSession(filename) {
        const res = await fetch(`/api/sessions/${filename}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Failed to delete session');
        return await res.json();
    },

    async deleteMessages(filename, indices) {
        const res = await fetch(`/api/sessions/${filename}/messages`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ indices })
        });
        if (!res.ok) throw new Error('Failed to delete messages');
        return await res.json();
    },

    // ── Memory / History ─────────────────────────────────────

    async fetchMemoryFile(fileType, agent) {
        const params = agent ? `?agent=${agent}` : '';
        const res = await fetch(`/api/memory/${fileType}${params}`);
        if (!res.ok) throw new Error(`Failed to fetch ${fileType}`);
        return await res.json();
    },

    async clearMemoryFile(fileType, agent) {
        const params = agent ? `?agent=${agent}` : '';
        const res = await fetch(`/api/memory/${fileType}${params}`, { method: 'DELETE' });
        if (!res.ok) throw new Error(`Failed to clear ${fileType}`);
        return await res.json();
    }
};
