/** @module components/MemoryPanel — History/Memory viewer (fork-local) */

import { useState, useEffect } from 'preact/hooks'
import { activePanel, panelExpanded, poolMode } from '../state/signals.js'
import { fetchMemory, clearMemory } from '../state/api.js'
import { AgentSelector } from './AgentSelector.jsx'
import { Markdown } from './Markdown.jsx'
import { formatSize, formatDate } from '../utils/format.js'
import { showToast } from './Toast.jsx'
import { renderMarkdown } from '../utils/markdown.js'

export function MemoryPanel() {
  const [tab, setTab] = useState('history')
  const [agent, setAgent] = useState(null)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const expanded = panelExpanded.value

  useEffect(() => {
    setLoading(true)
    fetchMemory(tab, agent)
      .then(d => setData(d))
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [tab, agent])

  async function handleClear() {
    if (!confirm(`Clear ${tab}?`)) return
    try {
      await clearMemory(tab, agent)
      setData({ ...data, content: '', size_bytes: 0 })
      showToast(`${tab} cleared`, 'success')
    } catch (e) {
      showToast(e.message, 'error')
    }
  }

  function renderContent() {
    if (loading) return <div class="loading-state"><div class="spinner" /></div>
    if (!data || data.info === 'selection_required') {
      return (
        <div class="memory-placeholder">
          <div class="memory-placeholder-icon">🤖</div>
          <div class="memory-placeholder-text">{data?.content || 'Select an agent'}</div>
        </div>
      )
    }
    if (!data.content) return <div class="memory-empty">File is empty</div>

    if (tab === 'history') {
      // Parse JSONL
      const entries = data.content.split('\n').filter(Boolean).map(line => {
        try { return JSON.parse(line) } catch { return null }
      }).filter(Boolean)

      return (
        <div class="memory-file-content">
          {entries.map((entry, i) => (
            <div key={i} style="margin-bottom:12px;padding:10px;border:1px solid var(--border-muted);border-radius:var(--radius-sm)">
              <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px">{entry.timestamp ? formatDate(entry.timestamp) : `#${i + 1}`}</div>
              <div style="font-size:13px;color:var(--text-primary)">{entry.role}: {typeof entry.content === 'string' ? entry.content.slice(0, 500) : JSON.stringify(entry.content).slice(0, 500)}</div>
            </div>
          ))}
          {entries.length === 0 && <pre>{data.content}</pre>}
        </div>
      )
    }

    // MEMORY.md
    return (
      <div class="memory-file-content">
        <div class="memory-file-content message-content" dangerouslySetInnerHTML={{ __html: renderMarkdown(data.content) }} />
      </div>
    )
  }

  return (
    <div class={`bottom-panel memory-panel-theme ${expanded ? 'expanded' : ''}`}>
      <div class="logs-header">
        <div style="display:flex;align-items:center;gap:12px">
          {poolMode.value && <AgentSelector value={agent} onChange={setAgent} />}
          <h3>🧠 Memory</h3>
          <div class="memory-tabs">
            <button class={`memory-tab ${tab === 'history' ? 'active' : ''}`} onClick={() => setTab('history')}>History</button>
            <button class={`memory-tab ${tab === 'memory' ? 'active' : ''}`} onClick={() => setTab('memory')}>Memory</button>
          </div>
        </div>
        <div class="logs-actions">
          <button class="btn-close-panel panel-expand-btn" onClick={() => panelExpanded.value = !expanded}>⤢</button>
          <button class="btn-close-panel" onClick={() => activePanel.value = null}>✕</button>
        </div>
      </div>
      {data && data.filename && (
        <div class="memory-file-header">
          <span class="memory-file-name">{data.filename}</span>
          <div class="memory-file-meta">
            <span class="memory-file-size">{formatSize(data.size_bytes)}</span>
            <button class="btn-clear-memory" onClick={handleClear} disabled={!data.content}>Clear</button>
          </div>
        </div>
      )}
      <div class="memory-panel-body">
        {renderContent()}
      </div>
    </div>
  )
}
