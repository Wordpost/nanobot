/**
 * Forensic Main Logic — Real-time SSE Edition
 */
import { state } from './state.js';
import { API } from './api.js';
import { UI } from './ui.js';
import { Router } from './router.js';
import { ConfigEditor } from './config-editor.js';

let logStream = null;
let sessionWatcher = null;
let deployStream = null;
let subagentWatcher = null;

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
        setupSubagentInteractivity();

        // Initialize the logic-driven UI blocks config editor
        window.configEditor = new ConfigEditor();
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

// ── System Deploy Stream (SSE) ──────────────────────────────

function startDeployStream() {
    stopDeployStream();
    UI.clearDeployLogs();
    UI.setDeployLiveIndicator(true);

    deployStream = API.streamDeploy((line, isError, isDone) => {
        UI.appendDeployLine(line, isError);
        if (isDone) {
            UI.setDeployLiveIndicator(false);
            if (deployStream) {
                deployStream.close();
                deployStream = null;
            }
        }
    }, () => {
        UI.setDeployLiveIndicator(false);
        if (deployStream) {
            deployStream.close();
            deployStream = null;
        }
    });
}

function startRestartStream() {
    stopDeployStream(); // re-use properties
    UI.clearDeployLogs();
    UI.setDeployLiveIndicator(true);

    deployStream = API.streamRestart((line, isError, isDone) => {
        UI.appendDeployLine(line, isError);
        if (isDone) {
            UI.setDeployLiveIndicator(false);
            if (deployStream) {
                deployStream.close();
                deployStream = null;
            }
        }
    }, () => {
        UI.setDeployLiveIndicator(false);
        if (deployStream) {
            deployStream.close();
            deployStream = null;
        }
    });
}

function stopDeployStream() {
    if (deployStream) {
        deployStream.close();
        deployStream = null;
    }
    UI.setDeployLiveIndicator(false);
}

// ── Subagent Panel ──────────────────────────────────────────

async function openSubagentPanel() {
    UI.dom.subagentPanel?.classList.remove('hidden');
    const badge = document.getElementById('subagent-badge');
    if (badge) badge.classList.remove('hidden');

    // Initial load
    try {
        const data = await API.fetchSubagents();
        UI.renderSubagentList(data.subagents);
    } catch (e) {
        console.error('Failed to load subagents:', e);
    }

    // Start watcher
    stopSubagentWatcher();
    subagentWatcher = API.watchSubagents((data) => {
        UI.renderSubagentList(data.subagents);
    }, () => {
        const badge = document.getElementById('subagent-badge');
        if (badge) badge.classList.add('hidden');
    });
}

function closeSubagentPanel() {
    UI.dom.subagentPanel?.classList.add('hidden');
    UI.dom.subagentPanel?.classList.remove('expanded');
    stopSubagentWatcher();
    const badge = document.getElementById('subagent-badge');
    if (badge) badge.classList.add('hidden');
}

function stopSubagentWatcher() {
    if (subagentWatcher) {
        subagentWatcher.close();
        subagentWatcher = null;
    }
}

async function loadSubagentDetail(filename) {
    try {
        const detail = await API.fetchSubagentDetail(filename);
        UI.renderSubagentDetail(detail);
        UI.setSubagentActiveItem(filename);
    } catch (e) {
        console.error('Failed to load subagent detail:', e);
    }
}

// Expose for Router.loadLogs
window.__nanobot_startLogStream = startLogStream;

// ── Subagent Interactivity (Delegation) ─────────────────────

function setupSubagentInteractivity() {
    // Global click delegation for subagent toggles + panel expand
    document.addEventListener('click', (e) => {
        // Panel expand/collapse button
        const expandBtn = e.target.closest('.panel-expand-btn');
        if (expandBtn) {
            const panelId = expandBtn.dataset.panel;
            const panel = document.getElementById(panelId);
            if (panel) {
                panel.classList.toggle('expanded');
                expandBtn.title = panel.classList.contains('expanded') ? 'Свернуть' : 'Развернуть';
            }
            return;
        }

        // Subagent card toggle (inline in chat)
        const cardToggle = e.target.closest('.subagent-card-toggle');
        if (cardToggle) {
            const card = cardToggle.closest('.subagent-card');
            const body = card?.querySelector('.subagent-card-body');
            const chevron = cardToggle.querySelector('.chevron');
            if (body) {
                body.classList.toggle('hidden');
                if (chevron) chevron.classList.toggle('open', !body.classList.contains('hidden'));

                // Lazy-load subagent detail into card body if has task-id
                const taskId = card?.dataset?.taskId;
                if (taskId && !body.dataset.loaded) {
                    body.dataset.loaded = 'true';
                    loadSubagentCardDetail(taskId, body);
                }
            }
            return;
        }

        // Subagent iteration toggle (in panel)
        const iterToggle = e.target.closest('.subagent-iter-toggle');
        if (iterToggle) {
            const iteration = iterToggle.closest('.subagent-iteration');
            const body = iteration?.querySelector('.subagent-iter-body');
            const chevron = iterToggle.querySelector('.chevron');
            if (body) {
                body.classList.toggle('hidden');
                if (chevron) chevron.classList.toggle('open', !body.classList.contains('hidden'));
            }
            return;
        }

        // Subagent tool call toggle (in panel)
        const tcToggle = e.target.closest('.subagent-tc-toggle');
        if (tcToggle) {
            const tc = tcToggle.closest('.subagent-tc');
            const detail = tc?.querySelector('.subagent-tc-detail');
            const chevron = tcToggle.querySelector('.chevron');
            if (detail) {
                detail.classList.toggle('hidden');
                if (chevron) chevron.classList.toggle('open', !detail.classList.contains('hidden'));
            }
            return;
        }

        // Subagent list item click (in panel)
        const listItem = e.target.closest('.subagent-list-item');
        if (listItem && listItem.dataset.filename) {
            loadSubagentDetail(listItem.dataset.filename);
            return;
        }
    });
}

async function loadSubagentCardDetail(taskId, containerEl) {
    try {
        // Find file matching task_id
        const data = await API.fetchSubagents();
        const match = data.subagents.find(s => s.task_id === taskId);
        if (!match) {
            containerEl.innerHTML = '<div class="subagent-task-desc">Subagent log not found for this task</div>';
            return;
        }

        const detail = await API.fetchSubagentDetail(match.filename);
        const statusClass = detail.status || 'unknown';
        const statusIcon = detail.status === 'ok' ? '✅' : detail.status === 'error' ? '❌' : '⏳';

        // Update the parent card status badge
        const card = containerEl.closest('.subagent-card');
        const statusBadge = card?.querySelector('.subagent-status');
        if (statusBadge) {
            statusBadge.className = `subagent-status ${statusClass}`;
            statusBadge.textContent = `${statusIcon} ${statusClass.toUpperCase()}`;
        }

        // Render mini detail
        let html = '';
        if (detail.task) {
            html += `<div class="subagent-task-desc">${UI.escapeHtml(detail.task)}</div>`;
        }
        if (detail.duration) {
            html += `<div style="font-size: 11px; color: var(--text-muted); margin-bottom: 8px;">Duration: ${UI.escapeHtml(detail.duration)}</div>`;
        }

        // Iterations (compact)
        if (detail.iterations && detail.iterations.length > 0) {
            html += detail.iterations.map(iter => {
                const toolsHtml = (iter.tool_calls || []).map(tc => `
                    <div class="subagent-tc">
                        <div class="subagent-tc-name subagent-tc-toggle">
                            🔧 ${UI.escapeHtml(tc.name)}
                            <span class="chevron">▶</span>
                        </div>
                        <div class="subagent-tc-detail hidden">
                            ${tc.arguments ? `<div class="subagent-tc-label">Args</div><pre>${UI.escapeHtml(tc.arguments)}</pre>` : ''}
                            ${tc.result ? `<div class="subagent-tc-label">Result</div><pre>${UI.escapeHtml(tc.result)}</pre>` : ''}
                        </div>
                    </div>
                `).join('');

                return `
                    <div class="subagent-iteration">
                        <div class="subagent-iter-header subagent-iter-toggle">
                            <span class="chevron">▶</span>
                            Iteration ${iter.number}
                            <span style="color: var(--text-muted); font-weight: 400;">(${(iter.tool_calls || []).length} tools)</span>
                        </div>
                        <div class="subagent-iter-body hidden">
                            ${iter.model_response ? `<div class="subagent-model-resp">${UI.escapeHtml(iter.model_response)}</div>` : ''}
                            ${toolsHtml}
                        </div>
                    </div>
                `;
            }).join('');
        }

        if (detail.final_result) {
            html += `<div class="subagent-final-result ${statusClass}">${UI.escapeHtml(detail.final_result)}</div>`;
        }

        containerEl.innerHTML = html;
    } catch (e) {
        containerEl.innerHTML = `<div class="subagent-task-desc">Error loading: ${e.message}</div>`;
    }
}

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
        UI.dom.logsPanel?.classList.remove('expanded');
        stopLogStream();
    });

    // Deploy panel open/close
    UI.dom.deployToggle?.addEventListener('click', () => {
        UI.dom.deployPanel?.classList.remove('hidden');
        startDeployStream();
    });

    UI.dom.restartToggle?.addEventListener('click', () => {
        UI.dom.deployPanel?.classList.remove('hidden');
        startRestartStream();
    });

    document.getElementById('btn-close-deploy')?.addEventListener('click', () => {
        UI.dom.deployPanel?.classList.add('hidden');
        UI.dom.deployPanel?.classList.remove('expanded');
        stopDeployStream();
    });

    // Subagent panel open/close
    UI.dom.subagentToggle?.addEventListener('click', () => {
        const panel = UI.dom.subagentPanel;
        if (panel && !panel.classList.contains('hidden')) {
            closeSubagentPanel();
        } else {
            openSubagentPanel();
        }
    });

    document.getElementById('btn-close-subagent')?.addEventListener('click', () => {
        closeSubagentPanel();
    });
}

init();

