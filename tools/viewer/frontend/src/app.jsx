/** @module App — Root component with hash-router (fork-local) */

import { useEffect, useRef } from 'preact/hooks'
import { Sidebar } from './components/Sidebar.jsx'
import { ChatView } from './components/ChatView.jsx'
import { LogsPanel } from './components/LogsPanel.jsx'
import { SubagentPanel } from './components/SubagentPanel.jsx'
import { MemoryPanel } from './components/MemoryPanel.jsx'
import { DeployPanel } from './components/DeployPanel.jsx'
import { ConfigEditor } from './components/ConfigEditor.jsx'
import { ToastContainer, showToast, dismissToast } from './components/Toast.jsx'
import { activePanel, activeSession, panelExpanded, sseStatus } from './state/signals.js'

export function App() {
  const panel = activePanel.value
  const session = activeSession.value
  const status = sseStatus.value
  const sseToastId = useRef(null)

  // Hash router
  useEffect(() => {
    function handleHash() {
      const hash = location.hash || ''
      const match = hash.match(/^#\/session\/(.+)/)
      if (match) {
        const hashSession = decodeURIComponent(match[1])
        if (activeSession.value !== hashSession) {
          activeSession.value = hashSession
        }
      } else if (activeSession.value) {
        activeSession.value = null
      }
    }
    handleHash()
    window.addEventListener('hashchange', handleHash)
    return () => window.removeEventListener('hashchange', handleHash)
  }, [])

  // Sync state to URL
  useEffect(() => {
    if (session) {
      history.replaceState(null, '', `#/session/${encodeURIComponent(session)}`)
    } else {
      history.replaceState(null, '', location.pathname + location.search)
    }
  }, [session])

  // persistent SSE toast
  useEffect(() => {
    if (status === 'error') {
      if (!sseToastId.current) {
        sseToastId.current = showToast('Connection lost, attempting to reconnect...', 'error', 0) // duration=0 for persistent
      }
    } else if (status === 'connected') {
      if (sseToastId.current) {
        dismissToast(sseToastId.current)
        sseToastId.current = null
        showToast('Connected to backend successfully', 'success', 3000)
      }
    }
  }, [status])

  // Close panel on Escape
  useEffect(() => {
    function handleKey(e) {
      if (e.key === 'Escape' && panel) {
        activePanel.value = null
        panelExpanded.value = false
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [panel])

  return (
    <>
      <Sidebar />
      <main class="main">
        <ChatView />
      </main>

      {/* Bottom panels */}
      {panel === 'logs' && <LogsPanel />}
      {panel === 'subagent' && <SubagentPanel />}
      {panel === 'memory' && <MemoryPanel />}
      {panel === 'deploy' && <DeployPanel />}
      {panel === 'config' && <ConfigEditor />}

      <ToastContainer />
    </>
  )
}
