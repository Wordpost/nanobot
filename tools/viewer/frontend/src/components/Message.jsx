/** @module components/Message — Single chat message (fork-local) */

import { useState } from 'preact/hooks'
import { Markdown } from './Markdown.jsx'
import { ToolCall } from './ToolCall.jsx'
import { SubagentCard } from './SubagentCard.jsx'
import { UsageBadge } from './UsageBadge.jsx'
import { extractThinkBlocks } from '../utils/format.js'
import { deleteMessages } from '../state/api.js'
import { activeSession, sessionDetail } from '../state/signals.js'
import { showToast } from './Toast.jsx'

export function Message({ msg, index, onRefresh }) {
  const [thinkOpen, setThinkOpen] = useState(false)
  const role = msg.role || 'system'
  const content = msg.content || ''
  const toolCalls = msg.tool_calls || []
  const subagentSpawns = msg.subagent_spawns || []
  const usage = msg.usage

  // Handle tool_result display
  const isToolResult = role === 'tool'
  const [toolContentOpen, setToolContentOpen] = useState(!isToolResult)

  // Extract <think> blocks
  const { clean, thinks } = extractThinkBlocks(content)
  const reasoningContent = msg.reasoning_content || msg.reasoning;

  async function handleDelete() {
    if (!confirm('Delete this message?')) return
    try {
      const filename = activeSession.value
      await deleteMessages(filename, [index])
      onRefresh?.()
      showToast('Message deleted', 'success')
    } catch (e) {
      showToast(`Delete failed: ${e.message}`, 'error')
    }
  }

  return (
    <div class={`message ${role}`}>
      {usage && (
        <div class="message-usage-container">
          {msg.model && <span class="message-model-info">{msg.model}</span>}
          <UsageBadge usage={usage} model={msg.model} />
        </div>
      )}

      <div class={`message-header ${isToolResult ? 'tool-toggle' : ''}`}
        onClick={isToolResult ? () => setToolContentOpen(!toolContentOpen) : undefined}>
        <span class="message-role">
          {isToolResult && <span class={`chevron ${toolContentOpen ? 'open' : ''}`}>▼</span>}
          {' '}{role}
          {msg.tool_name && <span class="tool-name-badge">{msg.tool_name}</span>}
        </span>
        <div class="message-header-right">
          {msg.timestamp && <span class="message-time">{new Date(msg.timestamp).toLocaleTimeString('ru-RU')}</span>}
          <button class="btn-delete-msg" onClick={handleDelete} title="Delete message">✕</button>
        </div>
      </div>

      {/* Thinking toggle */}
      {(thinks.length > 0 || reasoningContent) && (
        <div>
          <div class="reasoning-toggle" onClick={() => setThinkOpen(!thinkOpen)}>
            🧠 Reasoning {thinks.length > 0 ? `(${thinks.length})` : ''}
            <span class={`chevron ${thinkOpen ? 'open' : ''}`}>▼</span>
          </div>
          {thinkOpen && (
            <>
              {reasoningContent && <div class="reasoning-block"><Markdown text={reasoningContent} /></div>}
              {thinks.map((t, i) => (
                <div key={i} class="reasoning-block"><Markdown text={t} /></div>
              ))}
            </>
          )}
        </div>
      )}

      {/* Main content */}
      {toolContentOpen && clean && <Markdown text={clean} />}

      {/* Subagent spawns */}
      {subagentSpawns.map((spawn, i) => (
        <SubagentCard key={i} spawn={spawn} />
      ))}

      {/* Tool calls */}
      {toolCalls.length > 0 && (
        <div class="tool-calls">
          {toolCalls.map((tc, i) => <ToolCall key={i} call={tc} />)}
        </div>
      )}
    </div>
  )
}
