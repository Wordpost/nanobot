/**
 * Forensic Main Logic — Real-time SSE Edition
 */
import { state } from './state.js';
import { API } from './api.js';
import { UI } from './ui.js';
import { Router } from './router.js';

let logStream = null;
let sessionWatcher = null;

async function init() {
    try {
        const config = await API.fetchConfig();
        const initial = await API.fetchSessions();

        state.update({
            config,
            sessions: initial.sessions,
            filteredSessions: initial.sessions
        });

        UI.renderFilters(state.sessions);
        UI.renderSessionList(state.filteredSessions);
        if (UI.dom.count) UI.dom.count.textContent = initial.total;

        Router.init();
        setupEventListeners();
        startSessionWatcher();
    } catch (e) {
        console.error('Initialization error:', e);
    }
}

// ── Session Watcher (SSE) ──────────────────────────────────

function startSessionWatcher() {
    if (sessionWatcher) sessionWatcher.close();

    state._sessionSizes = {};
    state.sessions.forEach(s => { state._sessionSizes[s.filename] = s.size_bytes; });

    sessionWatcher = API.watchSessions((data) => {
        const activeFilename = state.activeSession?.filename;
        const prevSizes = { ...state._sessionSizes };

        const newSizes = {};
        data.sessions.forEach(s => { newSizes[s.filename] = s.size_bytes; });

        state.sessions = data.sessions;
        state.filter();

        UI.renderSessionList(state.filteredSessions, activeFilename);
        if (UI.dom.count) UI.dom.count.textContent = data.total;
        UI.pulseCount();

        // Auto-refresh active session only if its size actually changed
        if (activeFilename &&
            prevSizes[activeFilename] !== undefined &&
            prevSizes[activeFilename] !== newSizes[activeFilename]) {
            Router.loadSession(activeFilename);
        }

        state._sessionSizes = newSizes;
    }, () => {
        console.warn('Session watcher disconnected, reconnecting in 5s…');
        setTimeout(startSessionWatcher, 5000);
    });
}

// ── Docker Log Stream (SSE) ────────────────────────────────

function startLogStream() {
    stopLogStream();
    UI.clearLogs();
    UI.setLiveIndicator(true);

    logStream = API.streamLogs((line, isError) => {
        UI.appendLogLine(line, isError);
    }, () => {
        UI.setLiveIndicator(false);
        setTimeout(() => {
            if (!UI.dom.logsPanel.classList.contains('hidden')) {
                startLogStream();
            }
        }, 3000);
    });
}

function stopLogStream() {
    if (logStream) {
        logStream.close();
        logStream = null;
    }
    UI.setLiveIndicator(false);
}

// Expose for Router.loadLogs
window.__nanobot_startLogStream = startLogStream;

// ── Event Listeners ────────────────────────────────────────

function setupEventListeners() {
    UI.dom.search.addEventListener('input', (e) => {
        state.setSearch(e.target.value);
        UI.renderSessionList(state.filteredSessions, state.activeSession?.filename);
    });

    UI.dom.channelFilters?.addEventListener('click', (e) => {
        const chip = e.target.closest('.channel-chip');
        if (chip) {
            UI.dom.channelFilters.querySelectorAll('.channel-chip')
                .forEach(b => b.classList.remove('active'));
            chip.classList.add('active');
            state.setChannel(chip.dataset.channel);
            UI.renderSessionList(state.filteredSessions, state.activeSession?.filename);
        }
    });

    document.getElementById('btn-refresh-chat')?.addEventListener('click', () => {
        if (state.activeSession) Router.loadSession(state.activeSession.filename);
    });

    UI.dom.sessionList.addEventListener('click', (e) => {
        const item = e.target.closest('.session-item');
        if (item) window.location.hash = `#/session/${item.dataset.filename}`;
    });

    // Logs panel open/close
    UI.dom.logsToggle?.addEventListener('click', () => {
        UI.dom.logsPanel?.classList.toggle('hidden');
        if (UI.dom.logsPanel && !UI.dom.logsPanel.classList.contains('hidden')) {
            startLogStream();
        } else {
            stopLogStream();
        }
    });

    document.getElementById('btn-close-logs')?.addEventListener('click', () => {
        UI.dom.logsPanel?.classList.add('hidden');
        stopLogStream();
    });
}

init();
