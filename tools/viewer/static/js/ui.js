/**
 * Forensic UI Components (ES Module)
 */

export const UI = {
    dom: {
        get sessionList() { return document.getElementById('session-list'); },
        get chatView() { return document.getElementById('chat-view'); },
        get chatHeader() { return document.getElementById('chat-header'); },
        get messages() { return document.getElementById('chat-messages'); },
        get emptyState() { return document.getElementById('empty-state'); },
        get dockerLogs() { return document.getElementById('logs-content'); },
        get logsPanel() { return document.getElementById('logs-panel'); },
        get logsToggle() { return document.getElementById('logs-toggle'); },
        get search() { return document.getElementById('search-input'); },
        get count() { return document.getElementById('session-count'); },
        get badgeCount() { return document.getElementById('message-count-badge'); },
        get channelFilters() { return document.getElementById('channel-filters'); },
        get deployPanel() { return document.getElementById('deploy-panel'); },
        get deployToggle() { return document.getElementById('deploy-toggle'); },
        get restartToggle() { return document.getElementById('restart-toggle'); },
        get deployContent() { return document.getElementById('deploy-content'); },
        get subagentPanel() { return document.getElementById('subagent-panel'); },
        get subagentToggle() { return document.getElementById('subagent-toggle'); },
        get subagentListEl() { return document.getElementById('subagent-list'); },
        get subagentDetailEl() { return document.getElementById('subagent-detail'); },
        get memoryPanel() { return document.getElementById('memory-panel'); },
        get memoryToggle() { return document.getElementById('memory-toggle'); },
        get memoryContent() { return document.getElementById('memory-content'); },
        get configPanel() { return document.getElementById('config-modal'); }
    },

    escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    },

    renderContent(content) {
        if (!content) return '';

        // If content is an object, try to unwrap common string fields
        if (typeof content !== 'string') {
            const unwrapped = content.content || content.output || content.result || content.stdout || content.text;
            if (typeof unwrapped === 'string') {
                content = unwrapped;
            } else {
                return `<pre>${this.escapeHtml(JSON.stringify(content, null, 2))}</pre>`;
            }
        }

        return this.renderMarkdown(content);
    },

    /**
     * Inline formatting: bold, italic, code, links.
     * Operates on already-escaped HTML text.
     */
    renderInline(text) {
        if (!text) return '';
        let html = this.escapeHtml(text);
        // Inline code (before bold/italic to protect backtick content)
        html = html.replace(/`([^`\n]+)`/g, '<code class="inline-code">$1</code>');
        // Bold+Italic (***)
        html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
        // Bold
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        // Italic
        html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
        // Links [text](url)
        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
        return html;
    },

    /**
     * Block-level markdown: headers, lists, code blocks, HRs.
     * Processes text line-by-line for proper structure.
     */
    renderMarkdown(text) {
        if (!text) return '';
        const lines = text.split('\n');
        const out = [];
        let i = 0;

        while (i < lines.length) {
            const rawLine = lines[i];
            const prefixMatch = rawLine.match(/^(\s*\d+\|?\s+)(.*)/);
            const line = prefixMatch ? prefixMatch[2] : rawLine;
            const linePrefix = prefixMatch ? prefixMatch[1] : '';
            const trimmed = line.trim();

            // ── Code block ───────────────────────────
            if (trimmed.startsWith('```')) {
                const codeLines = [];
                i++;
                while (i < lines.length && !lines[i].trim().startsWith('```')) {
                    codeLines.push(lines[i]);
                    i++;
                }
                i++;
                out.push(`<pre class="code-block">${this.escapeHtml(codeLines.join('\n'))}</pre>`);
                continue;
            }

            // ── Header ───────────────────────────────
            const hMatch = trimmed.match(/^(#{1,6})\s*(.*)/);
            if (hMatch) {
                const lvl = hMatch[1].length;
                const hContent = hMatch[2].trim();
                if (hContent) {
                    const pre = linePrefix ? `<span class="md-line-prefix">${this.escapeHtml(linePrefix)}</span>` : '';
                    out.push(`<div class="md-h${lvl}">${pre}${this.renderInline(hContent)}</div>`);
                    i++;
                    continue;
                }
            }

            // ── Table ────────────────────────────────
            if (trimmed.startsWith('|')) {
                const tableLines = [];
                while (i < lines.length) {
                    const lRaw = lines[i];
                    const lMatch = lRaw.match(/^(\s*\d+\|?\s+)?\s*\|(.*)/);
                    if (!lMatch) break;
                    tableLines.push({ prefix: lMatch[1] || '', content: lMatch[2] });
                    i++;
                }

                if (tableLines.length > 0) {
                    let html = '<div class="md-table-wrapper"><table class="md-table">';
                    let hasHeader = false;

                    // Check for separator line |---|
                    if (tableLines.length > 1 && tableLines[1].content.trim().startsWith('---')) {
                        hasHeader = true;
                    }

                    tableLines.forEach((tl, idx) => {
                        if (hasHeader && idx === 1) return; // skip |---|
                        const cells = tl.content.split('|').filter((_, i, a) => i > 0 && i < a.length - 1 || tl.content.trim().split('|').length > 2);
                        // Clean up leading/trailing empty cells if present
                        const cleanCells = tl.content.split('|').map(c => c.trim()).filter((c, idx, arr) => {
                            if (idx === 0 && c === '') return false;
                            if (idx === arr.length - 1 && c === '') return false;
                            return true;
                        });

                        const tag = (hasHeader && idx === 0) ? 'th' : 'td';
                        if (idx === 0 && hasHeader) html += '<thead>';
                        if (idx === 2 && hasHeader || idx === 0 && !hasHeader) html += '<tbody>';

                        html += '<tr>' + cleanCells.map(c => `<${tag}>${this.renderInline(c)}</${tag}>`).join('') + '</tr>';

                        if (idx === 0 && hasHeader) html += '</thead>';
                    });

                    html += '</tbody></table></div>';
                    out.push(html);
                    continue;
                }
            }

            // ── Horizontal rule ──────────────────────
            if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
                out.push('<hr class="md-hr">');
                i++;
                continue;
            }

            // ── Unordered list ───────────────────────
            if (/^[-*]\s+/.test(trimmed)) {
                const items = [];
                while (i < lines.length) {
                    const lRaw = lines[i];
                    const lMatch = lRaw.match(/^(\s*\d+\|?\s+)?\s*[-*]\s+(.*)/);
                    if (!lMatch) break;
                    items.push(`<li>${this.renderInline(lMatch[2])}</li>`);
                    i++;
                }
                out.push(`<ul class="md-list">${items.join('')}</ul>`);
                continue;
            }

            // ── Ordered list ────────────────────────
            if (/^\d+\.\s+/.test(trimmed)) {
                const items = [];
                while (i < lines.length) {
                    const lRaw = lines[i];
                    const lMatch = lRaw.match(/^(\s*\d+\|?\s+)?\s*\d+\.\s+(.*)/);
                    if (!lMatch) break;
                    items.push(`<li>${this.renderInline(lMatch[2])}</li>`);
                    i++;
                }
                out.push(`<ol class="md-list">${items.join('')}</ol>`);
                continue;
            }

            // ── Empty line → spacer ─────────────────
            if (trimmed === '' && !linePrefix) {
                out.push('<div class="md-spacer"></div>');
                i++;
                continue;
            }

            // ── Regular text ────────────────────────
            const p = linePrefix ? `<span class="md-line-prefix">${this.escapeHtml(linePrefix)}</span>` : '';
            out.push(`${p}${this.renderInline(line)}<br>`);
            i++;
        }

        return out.join('');
    },


    renderSessionList(sessions, activeFilename) {
        if (!this.dom.sessionList) return;

        if (sessions.length === 0) {
            this.dom.sessionList.innerHTML = `
                <div class="empty-list">
                    <i class="fas fa-search"></i>
                    <span>HISTORY_EMPTY</span>
                </div>
            `;
            return;
        }

        this.dom.sessionList.innerHTML = sessions.map((s, idx) => {
            const isActive = activeFilename === s.filename;
            const agentBadge = s.agent
                ? `<span class="agent-badge">${this.escapeHtml(s.agent)}</span>`
                : '';

            return `
                <div class="session-item ${isActive ? 'active' : ''}" 
                     data-filename="${s.filename}"
                     style="--i: ${idx}">
                    <div class="session-key">
                        ${agentBadge}
                        <span class="channel-badge ${s.channel}">${s.channel}</span>
                    </div>
                    <div class="session-meta">
                        <span class="session-date">${s.updated_at ? this.formatDate(s.updated_at) : '...'}</span>
                        <div class="session-meta-right">
                            <span class="session-size">${this.formatSize(s.size_bytes)}</span>
                            <button class="btn-delete-session" data-filename="${s.filename}" title="Удалить сессию">
                                <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M4 4L12 12M12 4L4 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    },

    updateActiveSession(filename) {
        if (!this.dom.sessionList) return;
        this.dom.sessionList.querySelectorAll('.session-item').forEach(item => {
            item.classList.toggle('active', item.dataset.filename === filename);
        });
    },

    renderFilters(sessions, config) {
        const channels = ['all', ...new Set(sessions.map(s => s.channel))];
        this.dom.channelFilters.innerHTML = channels.map(c => `
            <div class="channel-chip ${c === 'all' ? 'active' : ''}" data-channel="${c}">
                ${c.toUpperCase()}
            </div>
        `).join('');

        // Agent filters (pool mode only)
        const agentFiltersEl = document.getElementById('agent-filters');
        if (agentFiltersEl && config?.pool_mode && config.agents?.length > 0) {
            agentFiltersEl.classList.remove('hidden');
            const agentNames = config.agents.map(a => typeof a === 'string' ? a : a.name);
            const all = ['all', ...agentNames];
            agentFiltersEl.innerHTML = all.map(a => `
                <div class="channel-chip agent-chip ${a === 'all' ? 'active' : ''}" data-agent="${a}">
                    ${a === 'all' ? 'ALL AGENTS' : a.toUpperCase()}
                </div>
            `).join('');
        }
    },

    renderMessages(session) {
        this.dom.emptyState.classList.add('hidden');
        this.dom.chatView.classList.remove('hidden');

        const displayKey = (session.metadata.key || '').replace(/^(telegram|webhook|api|heartbeat):/, '');
        const titleEl = document.getElementById('chat-title');
        const metaEl = document.getElementById('chat-meta');
        const countBadge = document.getElementById('message-count-badge');

        if (titleEl) titleEl.textContent = displayKey;
        if (metaEl) metaEl.textContent = `Updated: ${this.formatDate(session.metadata.updated_at)}`;
        if (countBadge) countBadge.textContent = `${session.total} MSG`;

        // Preserve scroll: auto-scroll only if user was near bottom
        const container = this.dom.messages;
        const wasAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 60;

        container.innerHTML = (session.messages || []).map((m, idx) => {
            const role = (m.role || 'system').toLowerCase();
            const dateObj = this.parseDate(m.timestamp);
            const time = dateObj ? dateObj.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';

            // Detect spawn tool call → render inline subagent card
            const spawnCard = this.renderSpawnCard(m);
            if (spawnCard) return spawnCard;

            return `
                <div class="message ${role}" style="--j: ${idx}" data-msg-index="${idx}">
                    <div class="message-header ${role === 'tool' ? 'tool-toggle' : ''}">
                        <span class="message-role">${role}</span>
                        <div class="message-header-right">
                            ${this.renderUsageBadge(m.usage)}
                            <span class="message-time">${time}</span>
                            <button class="btn-delete-msg" data-msg-index="${idx}" title="Удалить сообщение">
                                <svg width="11" height="11" viewBox="0 0 16 16" fill="none"><path d="M4 4L12 12M12 4L4 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
                            </button>
                            ${role === 'tool' ? '<i class="fas fa-chevron-down chevron"></i>' : ''}
                        </div>
                    </div>
                    <div class="message-content ${role === 'tool' ? 'hidden' : ''}">${this.renderContent(m.content)}</div>
                    
                    ${m.reasoning ? `
                        <div class="reasoning-toggle">
                            <i class="fas fa-brain"></i> REASONING <i class="fas fa-chevron-down chevron"></i>
                        </div>
                        <div class="reasoning-block hidden">${this.renderContent(m.reasoning)}</div>
                    ` : ''}
                    
                    ${this.renderToolCalls(m.tool_calls)}
                </div>
            `;
        }).join('');

        this.addMessageInteractivity();
        if (wasAtBottom) container.scrollTop = container.scrollHeight;
    },

    addMessageInteractivity() {
        if (!this.dom.messages || this._interactionsBound) return;

        this.dom.messages.addEventListener('click', (e) => {
            // Handle reasoning toggle
            const reasoningToggle = e.target.closest('.reasoning-toggle');
            if (reasoningToggle) {
                const parent = reasoningToggle.closest('.message');
                const block = parent ? parent.querySelector('.reasoning-block') : null;
                const chevron = reasoningToggle.querySelector('.chevron');
                if (block) {
                    block.classList.toggle('hidden');
                    if (chevron) chevron.classList.toggle('open', !block.classList.contains('hidden'));
                }
                return;
            }

            // Handle tool call toggle
            const toolHeader = e.target.closest('.tool-call-header');
            if (toolHeader) {
                const parent = toolHeader.closest('.tool-call');
                const body = parent ? parent.querySelector('.tool-call-body') : null;
                const chevron = toolHeader.querySelector('.chevron');
                if (body) {
                    body.classList.toggle('hidden');
                    if (chevron) chevron.classList.toggle('open', !body.classList.contains('hidden'));
                }
                return;
            }

            // Handle tool result toggle
            const toolToggle = e.target.closest('.tool-toggle');
            if (toolToggle) {
                const parent = toolToggle.closest('.message');
                const content = parent ? parent.querySelector('.message-content') : null;
                const chevron = toolToggle.querySelector('.chevron');
                if (content) {
                    content.classList.toggle('hidden');
                    if (chevron) chevron.classList.toggle('open', !content.classList.contains('hidden'));
                }
                return;
            }
        });

        this._interactionsBound = true;
    },

    renderToolCalls(calls) {
        if (!calls || !calls.length) return '';
        return `
            <div class="tool-calls">
                ${calls.map(c => `
                    <div class="tool-call">
                        <div class="tool-call-header">
                            <i class="fas fa-terminal"></i> <span>${c.function?.name || 'tool_call'}</span>
                            <i class="fas fa-chevron-down chevron"></i>
                        </div>
                        <div class="tool-call-body hidden">
                            <pre>${this.escapeHtml(c.function?.arguments || '')}</pre>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    },

    // ── Subagent Inline Cards ───────────────────────────────

    /**
     * Detect spawn tool calls or subagent result messages and render inline cards.
     * Returns HTML string if message is a spawn-related message, null otherwise.
     */
    renderSpawnCard(msg) {
        // 1. Detect tool result from 'spawn' call — message with tool_call_id and name='spawn'
        if (msg.role === 'tool' && msg.name === 'spawn' && typeof msg.content === 'string') {
            const idMatch = msg.content.match(/\(id:\s*([a-f0-9]+)\)/);
            const taskId = idMatch ? idMatch[1] : '';
            const labelMatch = msg.content.match(/Subagent\s+\[([^\]]+)\]/);
            const label = labelMatch ? labelMatch[1] : 'Subagent';

            return `
                <div class="subagent-card" data-task-id="${taskId}">
                    <div class="subagent-card-header subagent-card-toggle">
                        <div class="subagent-card-title">
                            <span class="icon">🤖</span>
                            SUBAGENT SPAWNED
                        </div>
                        <div class="subagent-card-meta">
                            <span class="subagent-status running">⏳ RUNNING</span>
                            <span class="subagent-duration">${this.escapeHtml(taskId)}</span>
                            <span class="chevron">▶</span>
                        </div>
                    </div>
                    <div class="subagent-card-body hidden">
                        <div class="subagent-task-desc">${this.escapeHtml(label)}</div>
                        <div class="loading-state" style="padding: 20px;"><div class="spinner"></div><span>Loading execution log...</span></div>
                    </div>
                </div>
            `;
        }

        // 2. Detect assistant message with spawn tool_calls
        if (msg.role === 'assistant' && msg.tool_calls) {
            const spawnCall = msg.tool_calls.find(tc => (tc.function?.name || tc.name) === 'spawn');
            if (spawnCall) {
                let args = {};
                try {
                    args = typeof spawnCall.function?.arguments === 'string'
                        ? JSON.parse(spawnCall.function.arguments)
                        : (spawnCall.function?.arguments || {});
                } catch { /* ignore */ }

                const dateObj = this.parseDate(msg.timestamp);
                const time = dateObj ? dateObj.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
                const otherCalls = msg.tool_calls.filter(tc => (tc.function?.name || tc.name) !== 'spawn');

                return `
                    <div class="message assistant" style="--j: 0">
                        <div class="message-header">
                            <span class="message-role">assistant</span>
                            <span class="message-time">${time}</span>
                        </div>
                        ${msg.content ? `<div class="message-content">${this.renderContent(msg.content)}</div>` : ''}
                        <div class="subagent-card">
                            <div class="subagent-card-header subagent-card-toggle">
                                <div class="subagent-card-title">
                                    <span class="icon">🚀</span>
                                    SPAWNING SUBAGENT: ${this.escapeHtml(args.label || (args.task || '').substring(0, 40))}
                                </div>
                                <div class="subagent-card-meta">
                                    <span class="chevron">▶</span>
                                </div>
                            </div>
                            <div class="subagent-card-body hidden">
                                <div class="subagent-task-desc">${this.escapeHtml(args.task || '')}</div>
                            </div>
                        </div>
                        ${this.renderToolCalls(otherCalls)}
                        ${msg.reasoning ? `
                            <div class="reasoning-toggle">
                                <i class="fas fa-brain"></i> REASONING <i class="fas fa-chevron-down chevron"></i>
                            </div>
                            <div class="reasoning-block hidden">${this.renderContent(msg.reasoning)}</div>
                        ` : ''}
                    </div>
                `;
            }
        }

        return null;
    },

    // ── Subagent Panel (Bottom Panel) ──────────────────────

    renderSubagentList(subagents) {
        const el = this.dom.subagentListEl;
        if (!el) return;

        if (!subagents || subagents.length === 0) {
            el.innerHTML = '<div class="subagent-panel-empty">No subagent executions found</div>';
            return;
        }

        el.innerHTML = subagents.map(s => `
            <div class="subagent-list-item" data-filename="${this.escapeHtml(s.filename)}">
                <div class="subagent-item-header">
                    <span class="subagent-list-label">${this.escapeHtml(s.label || s.filename)}</span>
                    <span class="subagent-list-id">${this.escapeHtml(s.task_id)}</span>
                        <div class="subagent-item-footer">
                    <div class="subagent-usage-block">
                        ${this.renderUsageBadge(s.usage)}
                    </div>
                    <div class="subagent-meta-block">
                        ${s.duration ? `<span class="subagent-duration">${this.escapeHtml(s.duration)}</span>` : ''}
                        <span class="subagent-status ${s.status}">${s.status === 'ok' ? '✅' : s.status === 'error' ? '❌' : '⏳'} ${s.status.toUpperCase()}</span>
                    </div>
                </div>
            </div>
        `).join('');
    },

    renderSubagentDetail(detail) {
        const el = this.dom.subagentDetailEl;
        if (!el) return;

        if (!detail) {
            el.innerHTML = '<div class="subagent-panel-empty">Select a subagent to view execution log</div>';
            return;
        }

        const statusClass = detail.status || 'unknown';
        const statusIcon = detail.status === 'ok' ? '✅' : detail.status === 'error' ? '❌' : '⏳';

        let html = `
            <div style="margin-bottom: 16px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
                <span class="subagent-status ${statusClass}">${statusIcon} ${(detail.status || 'unknown').toUpperCase()}</span>
                ${this.renderUsageBadge(detail.usage)}
                ${detail.duration ? `<span class="subagent-duration">${this.escapeHtml(detail.duration)}</span>` : ''}
                ${detail.started ? `<span class="subagent-duration">Started: ${this.escapeHtml(detail.started)}</span>` : ''}
            </div>
        `;

        if (detail.task) {
            html += `<div class="subagent-task-desc">${this.escapeHtml(detail.task)}</div>`;
        }

        // Iterations
        if (detail.iterations && detail.iterations.length > 0) {
            html += detail.iterations.map(iter => {
                const toolsHtml = (iter.tool_calls || []).map(tc => `
                    <div class="subagent-tc">
                        <div class="subagent-tc-name subagent-tc-toggle">
                            🔧 ${this.escapeHtml(tc.name)}
                            <span class="chevron">▶</span>
                        </div>
                        <div class="subagent-tc-detail hidden">
                            ${tc.arguments ? `<div class="subagent-tc-label">Arguments</div><pre>${this.escapeHtml(tc.arguments)}</pre>` : ''}
                            ${tc.result ? `<div class="subagent-tc-label">Result</div><pre>${this.escapeHtml(tc.result)}</pre>` : ''}
                        </div>
                    </div>
                `).join('');

                return `
                    <div class="subagent-iteration">
                        <div class="subagent-iter-header subagent-iter-toggle">
                            <span class="chevron">▶</span>
                            Iteration ${iter.number}
                            <span style="color: var(--text-muted); font-weight: 400;">(${(iter.tool_calls || []).length} tool calls)</span>
                            ${this.renderUsageBadge(iter.usage)}
                        </div>
                        <div class="subagent-iter-body hidden">
                            ${iter.model_response ? `<div class="subagent-model-resp">${this.escapeHtml(iter.model_response)}</div>` : ''}
                            ${toolsHtml}
                        </div>
                    </div>
                `;
            }).join('');
        }

        // Final result
        if (detail.final_result) {
            html += `<div class="subagent-final-result ${statusClass}">${this.escapeHtml(detail.final_result)}</div>`;
        }

        el.innerHTML = html;
    },

    setSubagentActiveItem(filename) {
        const el = this.dom.subagentListEl;
        if (!el) return;
        el.querySelectorAll('.subagent-list-item').forEach(item => {
            item.classList.toggle('active', item.dataset.filename === filename);
        });
    },

    renderLogs(logs) {
        this.dom.dockerLogs.innerHTML = logs.split('\n').map(line => {
            if (line.includes('[error]')) return `<div class="log-line error">${this.escapeHtml(line)}</div>`;
            return `<div class="log-line">${this.escapeHtml(line)}</div>`;
        }).join('');
        this.dom.dockerLogs.scrollTop = this.dom.dockerLogs.scrollHeight;
    },

    // ── Real-time log streaming helpers ─────────────────────

    appendLogLine(line, isError) {
        if (!this.dom.dockerLogs) return;
        const div = document.createElement('div');
        div.className = 'log-line' + (isError || (line && line.includes('[error]')) ? ' error' : '');
        div.textContent = line;
        this.dom.dockerLogs.appendChild(div);

        // Auto-scroll only if user is near bottom
        const el = this.dom.dockerLogs;
        const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        if (isNearBottom) el.scrollTop = el.scrollHeight;

        // Cap DOM at 1000 lines to prevent memory bloat
        while (this.dom.dockerLogs.children.length > 1000) {
            this.dom.dockerLogs.removeChild(this.dom.dockerLogs.firstChild);
        }
    },

    clearLogs() {
        if (this.dom.dockerLogs) this.dom.dockerLogs.innerHTML = '';
    },

    setLiveIndicator(active) {
        const badge = document.getElementById('live-badge');
        if (badge) badge.classList.toggle('hidden', !active);
    },

    appendDeployLine(line, isError) {
        if (!this.dom.deployContent) return;
        const div = document.createElement('div');
        div.className = 'log-line' + (isError || (line && line.includes('[ERROR]')) ? ' error' : '');
        div.textContent = line;
        this.dom.deployContent.appendChild(div);

        const el = this.dom.deployContent;
        const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        if (isNearBottom) el.scrollTop = el.scrollHeight;
    },

    clearDeployLogs() {
        if (this.dom.deployContent) this.dom.deployContent.innerHTML = '';
    },

    setDeployLiveIndicator(active) {
        const badge = document.getElementById('deploy-badge');
        if (badge) badge.classList.toggle('hidden', !active);
    },

    pulseCount() {
        const el = this.dom.count;
        if (!el) return;
        el.classList.remove('pulse');
        void el.offsetWidth; // force reflow to restart animation
        el.classList.add('pulse');
    },

    parseDate(ds) {
        if (!ds) return null;
        try {
            let str = ds;
            // Если это строка ISO без указания TZ (нет Z и нет +/- в конце), добавляем Z
            if (typeof str === 'string' && str.includes('T') && !str.endsWith('Z') && !str.includes('+')) {
                str += 'Z';
            }
            const d = new Date(str);
            return isNaN(d.getTime()) ? null : d;
        } catch (e) {
            return null;
        }
    },

    formatDate(ds) {
        const d = this.parseDate(ds);
        if (!d) return ds || '...';

        const now = new Date();
        const diff = (now - d) / 1000;
        if (diff < 60) return 'Just now';
        if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
        if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
        return d.toLocaleDateString();
    },

    formatSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / 1048576).toFixed(1) + ' MB';
    },

    // ── Memory Panel ────────────────────────────────────────

    renderMemoryPanel(data, fileType) {
        const el = this.dom.memoryContent;
        if (!el) return;

        // Check if this is a "Selection Required" placeholder
        if (data.info === 'selection_required' || (data.content && data.content.includes("Please select"))) {
            el.innerHTML = `
                <div class="memory-placeholder">
                    <div class="memory-placeholder-icon">📋</div>
                    <div class="memory-placeholder-text">${this.escapeHtml(data.content)}</div>
                </div>
            `;
            return;
        }

        const isEmpty = !data.content || data.content.trim() === '';
        const sizeStr = this.formatSize(data.size_bytes || 0);

        el.innerHTML = `
            <div class="memory-file-header">
                <div class="memory-file-name">${this.escapeHtml(data.filename || fileType.toUpperCase() + '.md')}</div>
                <div class="memory-file-meta">
                    <span class="memory-file-size">${sizeStr}</span>
                    <button class="btn-clear-memory" data-file-type="${fileType}" ${isEmpty ? 'disabled' : ''} title="Очистить содержимое">Очистить</button>
                </div>
            </div>
            <div class="memory-file-content">${isEmpty
                ? '<div class="memory-empty">Файл пуст</div>'
                : `<pre>${this.escapeHtml(data.content)}</pre>`
            }</div>
        `;
    },

    renderUsageBadge(usage) {
        if (!usage) return '';
        const prompt = usage.prompt_tokens || 0;
        const completion = usage.completion_tokens || 0;
        const cached = usage.cached_tokens || 0;
        const reqs = usage.requests || 0;
        const total = prompt + completion;
        if (total === 0) return '';

        const cachedPct = (cached && prompt) ? Math.round((cached / prompt) * 100) : 0;
        const cachedHtml = cachedPct > 0
            ? `<span class="usage-cached" title="Cached tokens">${cachedPct}% cached</span>`
            : '';
        const reqsHtml = reqs > 0
            ? `<span class="usage-reqs" title="API requests made"><svg width="10" height="10" viewBox="0 0 16 16" fill="none" style="margin-right: 2px;"><path d="M2 5l6 3 6-3-6-3-6 3z" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/><path d="M2 8l6 3 6-3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/><path d="M2 11l6 3 6-3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>${reqs}</span>`
            : '';
        const totalStr = total >= 1000 ? (total / 1000).toFixed(1) + 'k' : total;

        return `
            <span class="usage-badge" title="Prompt: ${prompt} | Completion: ${completion}${cached ? ' | Cached: ' + cached : ''}">
                <svg width="10" height="10" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5"/><path d="M8 4v4l3 2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
                ${totalStr}
                ${cachedHtml}
                ${reqsHtml}
            </span>
        `;
    },

    // ── Agent Selector (Pool Mode) ──────────────────────────

    /**
     * Render agent selector dropdown into a container.
     * @param {string} containerId - DOM element ID to render into
     * @param {Array} agents - AgentInfo array from config
     * @param {Object} [opts] - options
     * @param {boolean} [opts.includeAll] - add 'All' option
     * @param {string} [opts.defaultAgent] - pre-selected agent
     */
    renderAgentSelector(containerId, agents, opts = {}) {
        const container = document.getElementById(containerId);
        if (!container) return;
        if (!agents || agents.length === 0) {
            container.innerHTML = '';
            return;
        }

        const agentNames = agents.map(a => typeof a === 'string' ? a : a.name);
        const defaultVal = (opts.defaultAgent !== undefined && opts.defaultAgent !== null) ? opts.defaultAgent : agentNames[0];

        let options = '';
        if (opts.includeAll) {
            options += `<option value="" ${defaultVal === '' ? 'selected' : ''}>All Agents</option>`;
        }
        options += agentNames.map(name =>
            `<option value="${name}" ${name === defaultVal ? 'selected' : ''}>${name}</option>`
        ).join('');

        container.innerHTML = `<select class="agent-select" id="${containerId}-select">${options}</select>`;
    },

    /**
     * Get currently selected agent from a selector.
     * @param {string} containerId
     * @returns {string|null}
     */
    getSelectedAgent(containerId) {
        const select = document.getElementById(`${containerId}-select`);
        return select?.value || null;
    },

    /**
     * Synchronize all .agent-select elements with the current agent.
     * @param {string} agent - agent name or empty string for all
     */
    syncAgentSelectors(agent) {
        const selectors = document.querySelectorAll('.agent-select');
        selectors.forEach(s => {
            s.value = agent === 'all' ? '' : agent;
        });

        // Also update sidebar chips
        const chips = document.querySelectorAll('.agent-chip');
        chips.forEach(c => {
            c.classList.toggle('active', c.dataset.agent === agent);
        });
    }
};
