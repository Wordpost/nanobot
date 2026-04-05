/** @module components/ToolCall — Collapsible tool call block (fork-local) */

import { useState } from 'preact/hooks'

export function ToolCall({ call }) {
  const [open, setOpen] = useState(false)
  const name = call.name || call.function?.name || 'unknown'
  const args = call.input || call.function?.arguments || call.args || ''
  const argsStr = typeof args === 'string' ? args : JSON.stringify(args, null, 2)

  return (
    <div class="tool-call">
      <div class="tool-call-header" onClick={() => setOpen(!open)}>
        <span class={`chevron ${open ? 'open' : ''}`}>▶</span>
        <span>🔧 {name}</span>
      </div>
      {open && (
        <div class="tool-call-body">
          <pre>{argsStr}</pre>
        </div>
      )}
    </div>
  )
}
