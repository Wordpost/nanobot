/** @module components/Sidebar — Session list + filters + toolbar (fork-local) */

import { useEffect } from 'preact/hooks'
import { SessionItem } from './SessionItem.jsx'
import {
  sessions, sessionsTotal, sessionsLoading,
  searchQuery, activeChannel, activeAgent,
  filteredSessions, channels, agentNames,
  poolMode, sseStatus, activePanel,
} from '../state/signals.js'
import { fetchSessions, getSessionsWatchUrl } from '../state/api.js'
import { useSSE } from '../hooks/useSSE.js'
import { useKeyboard } from '../hooks/useKeyboard.js'

export function Sidebar() {
  const filtered = filteredSessions.value
  const allChannels = channels.value
  const allAgents = agentNames.value
  const loading = sessionsLoading.value
  const total = sessionsTotal.value
  const isPool = poolMode.value
  const status = sseStatus.value

  useKeyboard()

  // Initial fetch
  useEffect(() => {
    fetchSessions().then(data => {
      sessions.value = data.sessions || []
      sessionsTotal.value = data.total || 0
      poolMode.value = data.sessions?.some(s => s.agent) || false
      sessionsLoading.value = false
    }).catch(() => { sessionsLoading.value = false })
  }, [])

  // SSE watcher for live updates
  useSSE(getSessionsWatchUrl(), {
    onMessage: (data) => {
      if (data.sessions) {
        sessions.value = data.sessions
        sessionsTotal.value = data.total || data.sessions.length
        poolMode.value = data.sessions.some(s => s.agent) || false
      }
    },
    enabled: true,
  })

  // Determine SSE indicator style
  const sseColor = status === 'connected' ? 'var(--accent-green)' : (status === 'error' ? 'var(--accent-red)' : 'var(--accent-amber)')
  const sseAnim = status === 'connected' ? 'none' : 'pulse 1.5s infinite'

  return (
    <aside class="sidebar">
      {/* Header */}
      <div class="sidebar-header">
        <div class="logo">
          <span class="logo-icon">🔬</span>
          <span class="logo-text">Viewer</span>
        </div>
        <div style="display:flex;align-items:center;gap:8px">
          <span class="session-count">{total}</span>
          <span style={`width:8px;height:8px;border-radius:50%;background:${sseColor};animation:${sseAnim}`} title={`SSE: ${status}`} />
        </div>
      </div>

      {/* Search */}
      <div class="search-box">
        <span class="search-icon">🔍</span>
        <input
          type="text"
          placeholder="Search sessions..."
          value={searchQuery.value}
          onInput={e => searchQuery.value = e.target.value}
          id="search-input"
        />
      </div>

      {/* Channel filters */}
      {allChannels.length > 0 && (
        <div class="channel-filters">
          <span
            class={`channel-chip ${!activeChannel.value ? 'active' : ''}`}
            onClick={() => activeChannel.value = null}
          >All</span>
          {allChannels.map(ch => (
            <span
              key={ch}
              class={`channel-chip ${activeChannel.value === ch ? 'active' : ''}`}
              onClick={() => activeChannel.value = activeChannel.value === ch ? null : ch}
            >{ch}</span>
          ))}
        </div>
      )}

      {/* Agent filter (pool mode) */}
      {isPool && allAgents.length > 0 && (
        <div class="channel-filters">
          <span
            class={`channel-chip ${!activeAgent.value ? 'active' : ''}`}
            onClick={() => activeAgent.value = null}
          >All agents</span>
          {allAgents.map(ag => (
            <span
              key={ag}
              class={`channel-chip ${activeAgent.value === ag ? 'active' : ''}`}
              onClick={() => activeAgent.value = activeAgent.value === ag ? null : ag}
            >{ag}</span>
          ))}
        </div>
      )}

      {/* Session list */}
      <div class="session-list">
        {loading
          ? <div class="loading-state"><div class="spinner" /><span>Loading...</span></div>
          : filtered.length === 0
            ? <div class="empty-state" style="padding:20px"><p>
                {searchQuery.value || activeChannel.value
                  ? `No matches for "${searchQuery.value || activeChannel.value}"`
                  : 'No sessions found'}
              </p></div>
            : filtered.map((s, i) => <SessionItem key={s.filename} session={s} index={i} />)
        }
      </div>

      {/* Toolbar */}
      <div class="sidebar-toolbar">
        <div class="toolbar-group">
          <span class="toolbar-label">Panels</span>
          <div class="toolbar-buttons">
            <button class="toolbar-btn" onClick={() => activePanel.value = activePanel.value === 'logs' ? null : 'logs'}>
              📋 Logs
            </button>
            <button class="toolbar-btn" onClick={() => activePanel.value = activePanel.value === 'subagent' ? null : 'subagent'}>
              🤖 Subagents
            </button>
            <button class="toolbar-btn" onClick={() => activePanel.value = activePanel.value === 'memory' ? null : 'memory'}>
              🧠 Memory
            </button>
          </div>
          <div class="toolbar-buttons">
            <button class="toolbar-btn" onClick={() => activePanel.value = activePanel.value === 'deploy' ? null : 'deploy'}>
              🚀 Deploy
            </button>
            <button class="toolbar-btn" onClick={() => activePanel.value = activePanel.value === 'config' ? null : 'config'}>
              ⚙️ Config
            </button>
          </div>
        </div>
      </div>
    </aside>
  )
}
