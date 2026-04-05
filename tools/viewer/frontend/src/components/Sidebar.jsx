/** @module components/Sidebar — Session list + select filters + toolbar (fork-local) */

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

/** Inline SVG logo — Nanobot Forensic Viewer (fork-local) */
function LogoIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" class="logo-icon" style="width:28px;height:28px;">
      <defs>
        <linearGradient id="logo-grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style="stop-color:#ff6b1a" />
          <stop offset="100%" style="stop-color:#ff8a47" />
        </linearGradient>
      </defs>
      <circle cx="12" cy="12" r="10" stroke="url(#logo-grad)" stroke-width="1.5" fill="none" opacity="0.3" />
      <circle cx="12" cy="12" r="6" stroke="url(#logo-grad)" stroke-width="1.5" fill="none" opacity="0.6" />
      <circle cx="12" cy="12" r="2.5" fill="url(#logo-grad)" />
      <line x1="12" y1="2" x2="12" y2="6" stroke="url(#logo-grad)" stroke-width="1" opacity="0.4" />
      <line x1="12" y1="18" x2="12" y2="22" stroke="url(#logo-grad)" stroke-width="1" opacity="0.4" />
      <line x1="2" y1="12" x2="6" y2="12" stroke="url(#logo-grad)" stroke-width="1" opacity="0.4" />
      <line x1="18" y1="12" x2="22" y2="12" stroke="url(#logo-grad)" stroke-width="1" opacity="0.4" />
    </svg>
  )
}

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
  const sseColor = status === 'connected'
    ? 'var(--accent-green)'
    : (status === 'error' ? 'var(--accent-red)' : 'var(--accent-amber)')
  const sseAnim = status === 'connected' ? 'none' : 'pulse 1.5s infinite'

  return (
    <aside class="sidebar">
      {/* Header */}
      <div class="sidebar-header">
        <div class="logo">
          <LogoIcon />
          <span class="logo-text">Viewer</span>
        </div>
        <div style="display:flex;align-items:center;gap:6px">
          <span class="session-count">{total}</span>
          <span
            style={`width:8px;height:8px;border-radius:50%;background:${sseColor};animation:${sseAnim};box-shadow:0 0 6px ${sseColor}`}
            title={`SSE: ${status}`}
          />
        </div>
      </div>

      {/* Search + Filters row */}
      <div class="sidebar-filters">
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

        <div class="filter-selects">
          {/* Channel select */}
          {allChannels.length > 0 && (
            <select
              class="filter-select"
              value={activeChannel.value || ''}
              onChange={e => activeChannel.value = e.target.value || null}
            >
              <option value="">All channels</option>
              {allChannels.map(ch => (
                <option key={ch} value={ch}>{ch}</option>
              ))}
            </select>
          )}

          {/* Agent select (pool mode) */}
          {isPool && allAgents.length > 0 && (
            <select
              class="filter-select"
              value={activeAgent.value || ''}
              onChange={e => activeAgent.value = e.target.value || null}
            >
              <option value="">All agents</option>
              {allAgents.map(ag => (
                <option key={ag} value={ag}>{ag}</option>
              ))}
            </select>
          )}
        </div>
      </div>

      {/* Session list */}
      <div class="session-list">
        {loading
          ? <div class="loading-state"><div class="spinner" /><span>Loading...</span></div>
          : filtered.length === 0
            ? <div class="empty-state" style="padding:16px"><p>
                {searchQuery.value || activeChannel.value
                  ? `No matches for "${searchQuery.value || activeChannel.value}"`
                  : 'No sessions found'}
              </p></div>
            : filtered.map((s, i) => <SessionItem key={s.filename} session={s} index={i} />)
        }
      </div>

      {/* Toolbar — flex-wrap для автоматического переноса */}
      <div class="sidebar-toolbar">
        <div class="toolbar-group">
          <span class="toolbar-label">Panels</span>
          <div class="toolbar-buttons">
            <button
              class={`toolbar-btn ${activePanel.value === 'logs' ? 'active' : ''}`}
              onClick={() => activePanel.value = activePanel.value === 'logs' ? null : 'logs'}
            >
              📋 Logs
            </button>
            <button
              class={`toolbar-btn ${activePanel.value === 'subagent' ? 'active' : ''}`}
              onClick={() => activePanel.value = activePanel.value === 'subagent' ? null : 'subagent'}
            >
              🤖 Subagents
            </button>
            <button
              class={`toolbar-btn ${activePanel.value === 'memory' ? 'active' : ''}`}
              onClick={() => activePanel.value = activePanel.value === 'memory' ? null : 'memory'}
            >
              🧠 Memory
            </button>
            <button
              class={`toolbar-btn ${activePanel.value === 'deploy' ? 'active' : ''}`}
              onClick={() => activePanel.value = activePanel.value === 'deploy' ? null : 'deploy'}
            >
              🚀 Deploy
            </button>
            <button
              class={`toolbar-btn ${activePanel.value === 'config' ? 'active' : ''}`}
              onClick={() => activePanel.value = activePanel.value === 'config' ? null : 'config'}
            >
              ⚙️ Config
            </button>
          </div>
        </div>
      </div>
    </aside>
  )
}
