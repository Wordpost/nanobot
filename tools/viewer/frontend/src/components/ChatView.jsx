/** @module components/ChatView — Message list with header (fork-local) */

import { useEffect, useRef } from 'preact/hooks'
import { Message } from './Message.jsx'
import { EmptyState } from './EmptyState.jsx'
import { sessionDetail, sessionLoading, activeSession } from '../state/signals.js'
import { fetchSessionDetail, deleteSession } from '../state/api.js'
import { showToast } from './Toast.jsx'
import { useVirtualList } from '../hooks/useVirtualList.js'

export function ChatView() {
  const detail = sessionDetail.value
  const loading = sessionLoading.value
  const filename = activeSession.value
  const scrollRef = useRef(null)

  async function loadSession() {
    if (!filename) return
    sessionLoading.value = true
    try {
      const data = await fetchSessionDetail(filename)
      sessionDetail.value = data
      
      // Auto-scroll to bottom initially
      setTimeout(() => {
        if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
      }, 50)
      
    } catch (e) {
      showToast(`Load failed: ${e.message}`, 'error')
    } finally {
      sessionLoading.value = false
    }
  }

  useEffect(() => { loadSession() }, [filename])

  const meta = detail?.metadata || {}
  const messages = detail?.messages || []

  // Virtual List Integration
  const { virtualItems, totalHeight, offsetY } = useVirtualList({
    items: messages,
    containerRef: scrollRef,
    itemHeight: 120, // rough estimate
  })

  if (!filename) {
    return (
      <EmptyState icon="🖱️" title="Select a session" message="Choose a session from the sidebar to view its contents">
        <p style="font-size:0.9rem; color:var(--text-secondary); margin-top:20px;">
          <kbd style="padding:2px 6px; background:var(--surface-3); border-radius:4px; font-family:monospace;">Ctrl</kbd> + <kbd style="padding:2px 6px; background:var(--surface-3); border-radius:4px; font-family:monospace;">K</kbd> or <kbd style="padding:2px 6px; background:var(--surface-3); border-radius:4px; font-family:monospace;">/</kbd> to search<br/>
          <kbd style="padding:2px 6px; background:var(--surface-3); border-radius:4px; font-family:monospace;">↑</kbd> <kbd style="padding:2px 6px; background:var(--surface-3); border-radius:4px; font-family:monospace;">↓</kbd> to navigate sessions
        </p>
      </EmptyState>
    )
  }

  if (loading) {
    return <div class="loading-state"><div class="spinner" /><span>Loading session...</span></div>
  }

  if (!detail) return null

  async function handleDeleteSession() {
    if (!confirm(`Delete session ${filename}?`)) return
    try {
      await deleteSession(filename)
      activeSession.value = null
      sessionDetail.value = null
      showToast('Session deleted', 'success')
    } catch (e) {
      showToast(`Delete failed: ${e.message}`, 'error')
    }
  }

  return (
    <div class="chat-view">
      <div class="chat-header">
        <div>
          <div class="chat-title">{meta.key || filename}</div>
          <div class="chat-meta">{filename}</div>
        </div>
        <div class="chat-actions">
          <span class="message-count-badge">{messages.length} msg</span>
          <button class="btn-icon" onClick={loadSession} title="Refresh">🔄</button>
          <button class="btn-icon btn-icon-danger" onClick={handleDeleteSession} title="Delete session">🗑️</button>
        </div>
      </div>
      <div class="chat-messages" ref={scrollRef}>
        {messages.length === 0
          ? <EmptyState icon="💬" title="Empty session" message="No messages in this session yet" />
          : (
            <div style={{ height: `${totalHeight}px`, position: 'relative' }}>
              <div style={{ position: 'absolute', top: 0, left: 0, right: 0, transform: `translateY(${offsetY}px)` }}>
                {virtualItems.map(({ item, index, measureRef }) => (
                  <div key={index} ref={measureRef} style={{ display: 'flex', flexDirection: 'column' }}>
                    <Message msg={item} index={index} onRefresh={loadSession} />
                  </div>
                ))}
              </div>
            </div>
          )
        }
      </div>
    </div>
  )
}
