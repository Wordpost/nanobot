/** @module components/SubagentCard — Inline subagent spawn card (fork-local) */

import { useState } from 'preact/hooks'
import { Markdown } from './Markdown.jsx'

export function SubagentCard({ spawn }) {
  const [open, setOpen] = useState(false)
  if (!spawn) return null

  const label = spawn.agent_name || spawn.name || 'Subagent'
  const status = spawn.status || 'running'
  const statusClass = status === 'ok' ? 'ok' : status === 'error' ? 'error' : 'running'
  const duration = spawn.duration_ms ? `${(spawn.duration_ms / 1000).toFixed(1)}s` : ''

  return (
    <div class="subagent-card">
      <div class="subagent-card-header" onClick={() => setOpen(!open)}>
        <div class="subagent-card-title">
          <span class="icon">🤖</span>
          <span>SUBAGENT: {label}</span>
        </div>
        <div class="subagent-card-meta">
          <span class={`subagent-status ${statusClass}`}>
            {status === 'ok' ? '✓ OK' : status === 'error' ? '✕ ERROR' : '⟳ RUNNING'}
          </span>
          {duration && <span class="subagent-duration">{duration}</span>}
          <span class={`chevron ${open ? 'open' : ''}`}>▶</span>
        </div>
      </div>
      {open && (
        <div class="subagent-card-body">
          {spawn.task && <div class="subagent-task-desc">{spawn.task}</div>}
          {spawn.result && (
            <div>
              <div class="subagent-result-toolbar">
                <span>RESULT</span>
              </div>
              <div class={`subagent-result-container ${statusClass}`}>
                <div class="subagent-final-result">
                  <Markdown text={spawn.result} />
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
