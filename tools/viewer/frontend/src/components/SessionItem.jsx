/** @module components/SessionItem — Single session row (fork-local) */

import { formatDate, formatSize } from '../utils/format.js'
import { activeSession } from '../state/signals.js'
import { deleteSession } from '../state/api.js'
import { showToast } from './Toast.jsx'

export function SessionItem({ session, index }) {
  const isActive = activeSession.value === session.filename
  const channel = session.channel || 'default'

  function handleClick() {
    activeSession.value = session.filename
    location.hash = `#/session/${session.filename}`
  }

  async function handleDelete(e) {
    e.stopPropagation()
    if (!confirm(`Delete ${session.filename}?`)) return
    try {
      await deleteSession(session.filename)
      if (isActive) {
        activeSession.value = null
      }
      showToast('Session deleted', 'success')
    } catch (err) {
      showToast(`Delete failed: ${err.message}`, 'error')
    }
  }

  return (
    <div
      class={`session-item ${isActive ? 'active' : ''}`}
      style={`--i: ${index}`}
      onClick={handleClick}
      data-session-id={session.filename}
    >
      <button class="btn-delete-session" onClick={handleDelete} title="Delete">✕</button>
      <div class="session-key">
        <span>{session.key || session.filename}</span>
        <span class={`channel-badge ${channel}`}>{channel}</span>
      </div>
      <div class="session-meta">
        <span class="session-date">{formatDate(session.updated_at || session.created_at)}</span>
        <span class="session-size">{formatSize(session.size_bytes)}</span>
      </div>
      {session.agent && <span class="agent-badge">🤖 {session.agent}</span>}
    </div>
  )
}
