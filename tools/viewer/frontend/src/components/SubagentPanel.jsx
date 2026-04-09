/** @module components/SubagentPanel — Bottom panel for subagent logs (fork-local) */

import { useState, useEffect } from 'preact/hooks'
import { activePanel, panelExpanded, poolMode, subagentsList, activeSubagent, subagentDetail } from '../state/signals.js'
import { fetchSubagents, fetchSubagentDetail, getSubagentsWatchUrl } from '../state/api.js'
import { useSSE } from '../hooks/useSSE.js'
import { AgentSelector } from './AgentSelector.jsx'
import { Markdown } from './Markdown.jsx'
import { showToast } from './Toast.jsx'
import { formatTokens, formatDate, formatTime } from '../utils/format.js'

export function SubagentPanel() {
  const [agent, setAgent] = useState(null)
  const expanded = panelExpanded.value
  const list = subagentsList.value
  const selected = activeSubagent.value
  const detail = subagentDetail.value

  // Initial fetch
  useEffect(() => {
    fetchSubagents(agent).then(data => {
      subagentsList.value = data.subagents || []
    }).catch(() => {})
  }, [agent])

  // SSE watcher
  useSSE(getSubagentsWatchUrl(agent), {
    onMessage: (data) => {
      if (data.subagents) subagentsList.value = data.subagents
    },
  })

  // Load detail when selected
  useEffect(() => {
    if (!selected) { subagentDetail.value = null; return }
    fetchSubagentDetail(selected).then(d => {
      subagentDetail.value = d
    }).catch(e => showToast(e.message, 'error'))
  }, [selected])

  return (
    <div class={`bottom-panel subagent-panel-theme ${expanded ? 'expanded' : ''}`}>
      <div class="logs-header">
        <div style="display:flex;align-items:center;gap:8px">
          {poolMode.value && <AgentSelector value={agent} onChange={setAgent} />}
          <h3>🤖 Subagents</h3>
          <span class="session-count">{list.length}</span>
        </div>
        <div class="logs-actions">
          <button class="btn-close-panel panel-expand-btn" onClick={() => panelExpanded.value = !expanded}>⤢</button>
          <button class="btn-close-panel" onClick={() => activePanel.value = null}>✕</button>
        </div>
      </div>
      <div class="subagent-panel-layout">
        <div class="subagent-panel-sidebar">
          <div class="subagent-list">
            {list.map(s => (
              <div
                key={s.filename}
                class={`subagent-list-item ${selected === s.filename ? 'active' : ''}`}
                onClick={() => activeSubagent.value = s.filename}
              >
                <div class="subagent-item-header">
                  <span class="subagent-list-label">{s.label || s.filename}</span>
                  <span class={`subagent-status ${s.status || 'running'}`}>
                    {s.status === 'ok' ? '✓' : s.status === 'error' ? '✕' : '⟳'}
                  </span>
                </div>
                <div class="subagent-item-footer">
                  <span class="subagent-list-id">{s.filename}</span>
                  <div class="subagent-meta-block">
                    {s.finished && <span class="subagent-finished">{formatTime(s.finished)}</span>}
                    {s.duration && <span class="subagent-duration">{s.duration}</span>}
                    {s.iterations && <span>{s.iterations} iter</span>}
                  </div>
                </div>
              </div>
            ))}
            {list.length === 0 && <div class="subagent-panel-empty">No subagent logs found</div>}
          </div>
        </div>
        <div class="subagent-panel-detail">
          {!detail
            ? <div class="subagent-panel-empty">Select a subagent to view details</div>
            : (
              <div>
                <h3 style="color:var(--accent-orange);margin-bottom:12px">{detail.label || detail.filename}</h3>
                <div class="subagent-summary-stats">
                  {detail.usage && (
                    <div class="usage-grid">
                      <div class="usage-item"><span class="label">Tokens:</span> <span class="value">{formatTokens(detail.usage.total_tokens)}</span></div>
                      {detail.usage.cached_tokens > 0 && <div class="usage-item"><span class="label">Cached:</span> <span class="value">{formatTokens(detail.usage.cached_tokens)}</span></div>}
                      <div class="usage-item"><span class="label">Requests:</span> <span class="value">{detail.usage.requests}</span></div>
                      <div class="usage-item"><span class="label">Time:</span> <span class="value">{detail.duration || 'n/a'}</span></div>
                      <div class="usage-item"><span class="label">Finished:</span> <span class="value">{detail.finished ? formatTime(detail.finished) : 'n/a'}</span></div>
                    </div>
                  )}
                </div>
                {detail.task && <div class="subagent-task-desc">{detail.task}</div>}
                {detail.iterations?.map((iter, i) => (
                  <SubagentIteration key={i} iter={iter} index={i} />
                ))}
                {detail.final_result && (
                  <div>
                    <div class="subagent-result-toolbar"><span>FINAL RESULT</span></div>
                    <div class={`subagent-result-container ${detail.status || ''}`}>
                      <div class="subagent-final-result"><Markdown text={detail.final_result} /></div>
                    </div>
                  </div>
                )}
              </div>
            )
          }
        </div>
      </div>
    </div>
  )
}

function SubagentIteration({ iter, index }) {
  const [open, setOpen] = useState(index === 0)
  return (
    <div class="subagent-iteration">
      <div class="subagent-iter-header" onClick={() => setOpen(!open)}>
        <div style="display:flex;align-items:center;gap:8px;flex:1">
          <span class={`chevron ${open ? 'open' : ''}`}>▶</span>
          <span>Iteration {index + 1}</span>
        </div>
        {iter.usage && (
          <div class="iter-usage-badge">
            {formatTokens(iter.usage.total_tokens)} tokens
          </div>
        )}
      </div>
      {open && (
        <div class="subagent-iter-body">
          {iter.model_response && <div class="subagent-model-resp">{iter.model_response}</div>}
          {iter.tool_calls?.map((tc, i) => (
            <SubagentToolCall key={i} tc={tc} />
          ))}
        </div>
      )}
    </div>
  )
}

function SubagentToolCall({ tc }) {
  const [open, setOpen] = useState(false)
  const input = tc.arguments || tc.input
  const output = tc.result || tc.output

  return (
    <div class="subagent-tc">
      <div class="subagent-tc-name" onClick={() => setOpen(!open)}>
        <span class={`chevron ${open ? 'open' : ''}`}>▶</span>
        🔧 {tc.name || tc.function?.name || 'tool'}
      </div>
      {open && (
        <div class="subagent-tc-detail">
          {input && (
            <>
              <div class="subagent-tc-label">Input</div>
              <pre class="subagent-raw-input">{typeof input === 'string' ? input : JSON.stringify(input, null, 2)}</pre>
            </>
          )}
          {output && (
            <>
              <div class="subagent-tc-label">Result</div>
              <div class="message-content subagent-md-output">
                <Markdown text={typeof output === 'string' ? output : JSON.stringify(output, null, 2)} />
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
