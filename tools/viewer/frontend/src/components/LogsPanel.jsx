/** @module components/LogsPanel — Docker logs SSE stream (fork-local) */

import { useState, useRef, useEffect } from 'preact/hooks'
import { activePanel, panelExpanded, poolMode, activeAgent } from '../state/signals.js'
import { getLogsStreamUrl, triggerRestart } from '../state/api.js'
import { useSSE } from '../hooks/useSSE.js'
import { AgentSelector } from './AgentSelector.jsx'

export function LogsPanel() {
  const [lines, setLines] = useState([])
  const [agent, setAgent] = useState(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const [restarting, setRestarting] = useState(false)
  const scrollRef = useRef(null)
  const expanded = panelExpanded.value

  useSSE(getLogsStreamUrl(agent), {
    onMessage: (data) => {
      if (data.line != null) {
        setLines(prev => [...prev.slice(-2000), data])
      }
    },
    enabled: true,
  })

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [lines.length, autoScroll])

  async function handleRestart() {
    try {
      setRestarting(true)
      await triggerRestart(agent)
      setLines(prev => [...prev, { line: '> Container restarted successfully.', done: true }])
    } catch (e) {
      setLines(prev => [...prev, { line: `> Restart failed: ${e.message}`, error: true }])
    } finally {
      setRestarting(false)
    }
  }

  return (
    <div class={`bottom-panel ${expanded ? 'expanded' : ''}`}>
      <div class="logs-header">
        <div style="display:flex;align-items:center;gap:8px">
          {poolMode.value && <AgentSelector value={agent} onChange={setAgent} />}
          <h3>📋 Docker Logs</h3>
          <span class="live-badge">● LIVE</span>
        </div>
        <div class="logs-actions">
          <button class="btn-sm" onClick={handleRestart} disabled={restarting}>
            {restarting ? 'Restarting...' : '🔁 Restart'}
          </button>
          <button class="btn-sm" onClick={() => setAutoScroll(!autoScroll)}>
            {autoScroll ? '⏸ Pause' : '▶ Auto-scroll'}
          </button>
          <button class="btn-sm" onClick={() => setLines([])}>Clear</button>
          <button class="btn-close-panel panel-expand-btn" onClick={() => panelExpanded.value = !expanded}>
            <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M3 8h10M8 3v10" stroke="currentColor" stroke-width="2"/></svg>
          </button>
          <button class="btn-close-panel" onClick={() => activePanel.value = null}>✕</button>
        </div>
      </div>
      <div class="logs-content" ref={scrollRef}>
        {lines.map((l, i) => (
          <div key={i} class={`log-line ${l.error ? 'error' : ''}`}>{l.line}</div>
        ))}
        {lines.length === 0 && <div style="color:var(--text-muted)">Waiting for log output...</div>}
      </div>
    </div>
  )
}
