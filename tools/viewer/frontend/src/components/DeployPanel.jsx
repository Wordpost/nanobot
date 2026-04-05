/** @module components/DeployPanel — Deploy/Restart SSE stream (fork-local) */

import { useState, useRef, useEffect } from 'preact/hooks'
import { activePanel, panelExpanded, poolMode } from '../state/signals.js'
import { getDeployStreamUrl, getRestartStreamUrl } from '../state/api.js'
import { useSSE } from '../hooks/useSSE.js'
import { AgentSelector } from './AgentSelector.jsx'

export function DeployPanel() {
  const [mode, setMode] = useState(null) // null | 'deploy' | 'restart'
  const [agent, setAgent] = useState(null)
  const [lines, setLines] = useState([])
  const [running, setRunning] = useState(false)
  const scrollRef = useRef(null)
  const expanded = panelExpanded.value

  const url = mode === 'deploy' ? getDeployStreamUrl() :
              mode === 'restart' ? getRestartStreamUrl(agent) : null

  useSSE(url, {
    onMessage: (data) => {
      if (data.line != null) {
        setLines(prev => [...prev, data])
        if (data.done) setRunning(false)
      }
    },
    enabled: !!mode && running,
  })

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [lines.length])

  function start(m) {
    setMode(m)
    setLines([])
    setRunning(true)
  }

  return (
    <div class={`bottom-panel deploy-panel-theme ${expanded ? 'expanded' : ''}`}>
      <div class="logs-header">
        <div style="display:flex;align-items:center;gap:8px">
          {poolMode.value && <AgentSelector value={agent} onChange={setAgent} />}
          <h3>🚀 Deploy / Restart</h3>
          {running && <span class="live-badge" style="color:var(--accent-blue)">● RUNNING</span>}
        </div>
        <div class="logs-actions">
          <button class="btn-sm" onClick={() => start('deploy')} disabled={running}>Deploy All</button>
          <button class="btn-sm" onClick={() => start('restart')} disabled={running}>Restart</button>
          <button class="btn-close-panel" onClick={() => activePanel.value = null}>✕</button>
        </div>
      </div>
      <div class="logs-content" ref={scrollRef}>
        {lines.map((l, i) => (
          <div key={i} class={`log-line ${l.error ? 'error' : ''}`}>
            {l.done ? (l.error ? '❌ ' : '✅ ') : ''}{l.line}
          </div>
        ))}
        {lines.length === 0 && <div style="color:var(--text-muted)">Click Deploy or Restart to begin...</div>}
      </div>
    </div>
  )
}
