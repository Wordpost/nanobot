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
        get deployContent() { return document.getElementById('deploy-content'); }
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
            const displayKey = (s.key || s.filename).replace(/^(telegram|webhook|api|heartbeat):/, '');
            
            return `
                <div class="session-item ${isActive ? 'active' : ''}" 
                     data-filename="${s.filename}"
                     style="--i: ${idx}">
                    <div class="session-key">
                        <span class="channel-badge ${s.channel}">${s.channel}</span>
                        <span>${this.escapeHtml(displayKey)}</span>
                    </div>
                    <div class="session-meta">
                        <span class="session-date">${s.updated_at ? this.formatDate(s.updated_at) : '...'}</span>
                        <span class="session-size">${this.formatSize(s.size_bytes)}</span>
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

    renderFilters(sessions) {
        const channels = ['all', ...new Set(sessions.map(s => s.channel))];
        this.dom.channelFilters.innerHTML = channels.map(c => `
            <div class="channel-chip ${c === 'all' ? 'active' : ''}" data-channel="${c}">
                ${c.toUpperCase()}
            </div>
        `).join('');
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
            
            return `
                <div class="message ${role}" style="--j: ${idx}">
                    <div class="message-header ${role === 'tool' ? 'tool-toggle' : ''}">
                        <span class="message-role">${role}</span>
                        <span class="message-time">${time}</span>
                        ${role === 'tool' ? '<i class="fas fa-chevron-down chevron"></i>' : ''}
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
        if (diff < 3600) return Math.floor(diff/60) + 'm ago';
        if (diff < 86400) return Math.floor(diff/3600) + 'h ago';
        return d.toLocaleDateString();
    },

    formatSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1048576) return (bytes/1024).toFixed(1) + ' KB';
        return (bytes/1048576).toFixed(1) + ' MB';
    }
};
