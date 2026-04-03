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

        UI.renderFilters(state.sessions, config);
        UI.renderSessionList(state.filteredSessions);
        if (UI.dom.count) UI.dom.count.textContent = initial.total;

        // Pool mode: render agent selectors in all panels
        if (config.pool_mode && config.agents?.length > 0) {
            const agent = state.activeAgent === 'all' ? '' : state.activeAgent;
            UI.renderAgentSelector('logs-agent-selector', config.agents, { defaultAgent: agent });
            UI.renderAgentSelector('restart-agent-selector', config.agents, { defaultAgent: agent });
            UI.renderAgentSelector('memory-agent-selector', config.agents, { includeAll: true, defaultAgent: agent });
            UI.renderAgentSelector('subagent-agent-selector', config.agents, { includeAll: true, defaultAgent: agent });
            UI.renderAgentSelector('config-agent-selector', config.agents, { defaultAgent: agent });
        }

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

    const agent = state.activeAgent === 'all' ? '' : state.activeAgent;
    logStream = API.streamLogs((line, isError) => {
        UI.appendLogLine(line, isError);
    }, () => {
        UI.setLiveIndicator(false);
        setTimeout(() => {
            if (!UI.dom.logsPanel.classList.contains('hidden')) {
                startLogStream();
            }
        }, 3000);
    }, agent);
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
    UI.dom.deployPanel?.classList.remove('hidden');
    UI.dom.deployToggle?.classList.add('active');
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
    const agent = UI.getSelectedAgent('restart-agent-selector');
    if (!agent) {
        alert('Please select an agent to restart.');
        return;
    }

    stopDeployStream();
    UI.clearDeployLogs();
    UI.dom.deployPanel?.classList.remove('hidden');
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
    }, agent);
}

function stopDeployStream() {
    if (deployStream) {
        deployStream.close();
        deployStream = null;
    }
    UI.setDeployLiveIndicator(false);
}

// ── Subagent Panel ──────────────────────────────────────────

async function openSubagentPanel(refreshOnly = false) {
    if (!refreshOnly) {
        UI.dom.subagentPanel?.classList.remove('hidden');
        const badge = document.getElementById('subagent-badge');
        if (badge) badge.classList.remove('hidden');
    }
    
    // Always clear detail view when switching/opening panel
    if (UI.dom.subagentDetailEl) {
        UI.dom.subagentDetailEl.innerHTML = '<div class="subagent-panel-empty">Select a subagent to view execution log</div>';
    }

    const agent = state.activeAgent === 'all' ? '' : state.activeAgent;
    
    try {
        const data = await API.fetchSubagents(agent);
        UI.renderSubagentList(data.subagents);
    } catch (e) {
        console.error('Failed to load subagents:', e);
    }

    stopSubagentWatcher();
    subagentWatcher = API.watchSubagents((data) => {
        UI.renderSubagentList(data.subagents);
    }, () => {
        const badge = document.getElementById('subagent-badge');
        if (badge) badge.classList.add('hidden');
    }, agent);
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
    // ── Global State Sync ─────────────────────────────────────
    state.subscribe(() => {
        const agentValue = state.activeAgent === 'all' ? '' : state.activeAgent;
        
        // 1. Sync all agent selectors in the UI to match global state
        UI.syncAgentSelectors(agentValue);
        
        // 2. Refresh open panels
        if (UI.dom.logsPanel && !UI.dom.logsPanel.classList.contains('hidden')) {
            startLogStream();
        }
        
        if (UI.dom.subagentPanel && !UI.dom.subagentPanel.classList.contains('hidden')) {
            openSubagentPanel(true);
        }
        
        if (UI.dom.memoryPanel && !UI.dom.memoryPanel.classList.contains('hidden')) {
            const activeTab = UI.dom.memoryPanel.querySelector('.memory-tab.active');
            loadMemoryFile(activeTab?.dataset.tab || 'history');
        }
        
        // 3. Sync Config Modal if open
        if (window.configEditor && UI.dom.configPanel && UI.dom.configPanel.classList.contains('open')) {
            window.configEditor.load();
        }
    });

    // Listen for all agent selector changes
    document.addEventListener('change', (e) => {
        if (e.target.classList.contains('agent-select')) {
            const agent = e.target.value || 'all';
            if (state.activeAgent !== agent) {
                state.setAgent(agent);
            }
        }
    });

    UI.dom.search.addEventListener('input', (e) => {
        state.setSearch(e.target.value);
        UI.renderSessionList(state.filteredSessions, state.activeSession?.filename);
    });

    UI.dom.channelFilters?.addEventListener('click', (e) => {
        const chip = e.target.closest('.channel-chip:not(.agent-chip)');
        if (chip) {
            UI.dom.channelFilters.querySelectorAll('.channel-chip')
                .forEach(b => b.classList.remove('active'));
            chip.classList.add('active');
            state.setChannel(chip.dataset.channel);
            UI.renderSessionList(state.filteredSessions, state.activeSession?.filename);
        }
    });

    document.getElementById('agent-filters')?.addEventListener('click', (e) => {
        const chip = e.target.closest('.agent-chip');
        if (chip) {
            document.querySelectorAll('.agent-chip')
                .forEach(b => b.classList.remove('active'));
            chip.classList.add('active');
            const agent = chip.dataset.agent;
            state.setAgent(agent);
            UI.renderSessionList(state.filteredSessions, state.activeSession?.filename);
        }
    });

    document.getElementById('btn-refresh-chat')?.addEventListener('click', () => {
        if (state.activeSession) Router.loadSession(state.activeSession.filename);
    });

    // Session list click — navigate or delete
    UI.dom.sessionList.addEventListener('click', (e) => {
        // Delete button clicked
        const delBtn = e.target.closest('.btn-delete-session');
        if (delBtn) {
            e.stopPropagation();
            const filename = delBtn.dataset.filename;
            if (confirm(`Удалить сессию ${filename}?`)) {
                API.deleteSession(filename).then(() => {
                    if (state.activeSession?.filename === filename) {
                        state.update({ activeSession: null });
                        UI.dom.chatView.classList.add('hidden');
                        UI.dom.emptyState.classList.remove('hidden');
                        window.location.hash = '';
                    }
                }).catch(err => console.error('Delete session error:', err));
            }
            return;
        }
        const item = e.target.closest('.session-item');
        if (item) window.location.hash = `#/session/${item.dataset.filename}`;
    });

    // Delete session from chat header
    document.getElementById('btn-delete-session')?.addEventListener('click', () => {
        const filename = state.activeSession?.filename;
        if (!filename) return;
        if (confirm(`Удалить сессию ${filename}?`)) {
            API.deleteSession(filename).then(() => {
                state.update({ activeSession: null });
                UI.dom.chatView.classList.add('hidden');
                UI.dom.emptyState.classList.remove('hidden');
                window.location.hash = '';
            }).catch(err => console.error('Delete session error:', err));
        }
    });

    // Delete message from chat
    UI.dom.messages?.addEventListener('click', (e) => {
        const delMsgBtn = e.target.closest('.btn-delete-msg');
        if (delMsgBtn) {
            e.stopPropagation();
            const idx = parseInt(delMsgBtn.dataset.msgIndex, 10);
            const filename = state.activeSession?.filename;
            if (!filename || isNaN(idx)) return;
            if (confirm(`Удалить сообщение #${idx + 1}?`)) {
                API.deleteMessages(filename, [idx]).then(() => {
                    Router.loadSession(filename);
                }).catch(err => console.error('Delete message error:', err));
            }
            return;
        }
    });

    // Helper to close all bottom panels except one (if provided)
    function closeAllPanels(exceptId = null) {
        const panels = ['logs-panel', 'subagent-panel', 'memory-panel', 'deploy-panel'];
        const toggles = ['logs-toggle', 'subagent-toggle', 'memory-toggle', 'deploy-toggle'];
        
        panels.forEach((id, idx) => {
            if (id === exceptId) return;
            const p = document.getElementById(id);
            if (p) {
                p.classList.add('hidden');
                p.classList.remove('expanded');
            }
            const t = document.getElementById(toggles[idx]);
            if (t) t.classList.remove('active');
            
            // Specific stop functions
            if (id === 'logs-panel') stopLogStream();
            if (id === 'deploy-panel') stopDeployStream();
            if (id === 'subagent-panel') stopSubagentWatcher();
        });
    }

    // Logs panel open/close
    UI.dom.logsToggle?.addEventListener('click', () => {
        const isOpen = !UI.dom.logsPanel?.classList.contains('hidden');
        if (isOpen) {
            UI.dom.logsPanel?.classList.add('hidden');
            UI.dom.logsToggle?.classList.remove('active');
            stopLogStream();
        } else {
            closeAllPanels('logs-panel');
            UI.dom.logsPanel?.classList.remove('hidden');
            UI.dom.logsToggle?.classList.add('active');
            startLogStream();
        }
    });

    document.getElementById('btn-close-logs')?.addEventListener('click', () => {
        UI.dom.logsPanel?.classList.add('hidden');
        UI.dom.logsPanel?.classList.remove('expanded');
        UI.dom.logsToggle?.classList.remove('active');
        stopLogStream();
    });

    // Deploy panel open/close
    UI.dom.deployToggle?.addEventListener('click', () => {
        const isOpen = !UI.dom.deployPanel?.classList.contains('hidden');
        if (isOpen) {
            UI.dom.deployPanel?.classList.add('hidden');
            UI.dom.deployToggle?.classList.remove('active');
            stopDeployStream();
        } else {
            closeAllPanels('deploy-panel');
            UI.dom.deployPanel?.classList.remove('hidden');
            UI.dom.deployToggle?.classList.add('active');
            startDeployStream();
        }
    });

    UI.dom.restartToggle?.addEventListener('click', () => {
        // Toggle behavior for restart (uses deploy panel)
        const isPanelOpen = !UI.dom.deployPanel?.classList.contains('hidden');
        if (isPanelOpen) {
            // Already there, just fire restart
            startRestartStream();
        } else {
            closeAllPanels('deploy-panel');
            startRestartStream();
        }
    });

    document.getElementById('btn-close-deploy')?.addEventListener('click', () => {
        UI.dom.deployPanel?.classList.add('hidden');
        UI.dom.deployPanel?.classList.remove('expanded');
        UI.dom.deployToggle?.classList.remove('active');
        stopDeployStream();
    });

    // Subagent panel open/close
    UI.dom.subagentToggle?.addEventListener('click', () => {
        const panel = UI.dom.subagentPanel;
        const isOpen = panel && !panel.classList.contains('hidden');
        if (isOpen) {
            closeSubagentPanel();
            UI.dom.subagentToggle?.classList.remove('active');
        } else {
            closeAllPanels('subagent-panel');
            openSubagentPanel();
            UI.dom.subagentToggle?.classList.add('active');
        }
    });

    document.getElementById('btn-close-subagent')?.addEventListener('click', () => {
        closeSubagentPanel();
        UI.dom.subagentToggle?.classList.remove('active');
    });

    // ── Memory Panel ──────────────────────────────────────

    UI.dom.memoryToggle?.addEventListener('click', () => {
        const panel = UI.dom.memoryPanel;
        const isOpen = panel && !panel.classList.contains('hidden');
        if (isOpen) {
            panel.classList.add('hidden');
            UI.dom.memoryToggle?.classList.remove('active');
        } else {
            closeAllPanels('memory-panel');
            panel?.classList.remove('hidden');
            UI.dom.memoryToggle?.classList.add('active');
            // Load active tab
            const activeTab = panel?.querySelector('.memory-tab.active');
            const fileType = activeTab?.dataset.tab || 'history';
            loadMemoryFile(fileType);
        }
    });

    document.getElementById('btn-close-memory')?.addEventListener('click', () => {
        UI.dom.memoryPanel?.classList.add('hidden');
        UI.dom.memoryPanel?.classList.remove('expanded');
        UI.dom.memoryToggle?.classList.remove('active');
    });

    // Memory tab switching
    document.querySelector('.memory-tabs')?.addEventListener('click', (e) => {
        const tab = e.target.closest('.memory-tab');
        if (!tab) return;
        document.querySelectorAll('.memory-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        loadMemoryFile(tab.dataset.tab);
    });

    // Memory clear button (delegated)
    UI.dom.memoryContent?.addEventListener('click', (e) => {
        const clearBtn = e.target.closest('.btn-clear-memory');
        if (!clearBtn) return;
        const fileType = clearBtn.dataset.fileType;
        const agent = state.activeAgent === 'all' ? '' : state.activeAgent;
        if (confirm(`Очистить содержимое ${fileType.toUpperCase()}.md? Файл не будет удалён.`)) {
            API.clearMemoryFile(fileType, agent).then(() => {
                loadMemoryFile(fileType);
            }).catch(err => console.error('Clear memory error:', err));
        }
    });
}

async function loadMemoryFile(fileType) {
    try {
        const agent = state.activeAgent === 'all' ? '' : state.activeAgent;
        const data = await API.fetchMemoryFile(fileType, agent);
        UI.renderMemoryPanel(data, fileType);
    } catch (e) {
        console.error('Failed to load memory file:', e);
    }
}

init();
