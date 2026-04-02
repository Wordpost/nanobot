/**
 * Forensic Hash Router (ES Module)
 */
import { state } from './state.js';
import { API } from './api.js';
import { UI } from './ui.js';

export const Router = {
    async resolve() {
        const hash = window.location.hash;
        
        if (hash.startsWith('#/session/')) {
            const filename = hash.replace('#/session/', '');
            await this.loadSession(filename);
        } else if (hash === '#/logs') {
            await this.loadLogs();
        } else {
            // Default to empty state
            state.update({ activeSession: null });
        }
    },

    async loadSession(filename) {
        state.update({ isLoading: true });
        try {
            const data = await API.fetchSessionDetail(filename);
            state.update({ activeSession: { filename, ...data }, isLoading: false });
            UI.renderMessages(state.activeSession);
            UI.updateActiveSession(filename);
        } catch (e) {
            console.error('Routing error:', e);
            state.update({ isLoading: false });
        }
    },

    async loadLogs() {
        UI.dom.logsPanel.classList.remove('hidden');
        // Trigger SSE stream start (managed by main.js)
        if (window.__nanobot_startLogStream) {
            window.__nanobot_startLogStream();
        } else {
            // Fallback: one-shot fetch
            const logsData = await API.fetchLogs();
            state.update({ logs: logsData.logs });
            UI.renderLogs(state.logs);
        }
    },

    navigate(path) {
        window.location.hash = path;
    },

    init() {
        window.addEventListener('hashchange', () => this.resolve());
        this.resolve();
    }
};
