/** @module state/signals — Reactive state via @preact/signals (fork-local) */

import { signal, computed } from '@preact/signals'

// ── Session list ───────────────────────────
export const sessions = signal([])
export const sessionsTotal = signal(0)
export const sessionsLoading = signal(true)

// ── Filters ────────────────────────────────
export const searchQuery = signal('')
export const activeChannel = signal(null)  // null = all
export const activeAgent = signal(null)    // pool mode agent filter

// ── Active session ─────────────────────────
export const activeSession = signal(null)   // filename
export const sessionDetail = signal(null)   // { metadata, messages, total }
export const sessionLoading = signal(false)

// ── Panels ─────────────────────────────────
export const activePanel = signal(null)     // 'logs' | 'subagent' | 'memory' | 'deploy' | 'config' | null
export const panelExpanded = signal(false)

// ── Pool mode ──────────────────────────────
export const poolMode = signal(false)
export const agents = signal([])

// ── Subagents ──────────────────────────────
export const subagentsList = signal([])
export const activeSubagent = signal(null)  // filename
export const subagentDetail = signal(null)

// ── SSE status ─────────────────────────────
export const sseStatus = signal('connecting') // 'connecting', 'connected', 'error'

// ── Config ─────────────────────────────────
export const configData = signal(null)

// ── Computed ───────────────────────────────
export const filteredSessions = computed(() => {
  let list = sessions.value
  const q = searchQuery.value.toLowerCase().trim()
  const ch = activeChannel.value
  const ag = activeAgent.value

  if (q) {
    list = list.filter(s =>
      (s.key || '').toLowerCase().includes(q) ||
      (s.filename || '').toLowerCase().includes(q)
    )
  }
  if (ch) {
    list = list.filter(s => s.channel === ch)
  }
  if (ag) {
    list = list.filter(s => s.agent === ag)
  }
  return list
})

export const channels = computed(() => {
  const set = new Set()
  sessions.value.forEach(s => { if (s.channel) set.add(s.channel) })
  return Array.from(set).sort()
})

export const agentNames = computed(() => {
  const set = new Set()
  sessions.value.forEach(s => { if (s.agent) set.add(s.agent) })
  return Array.from(set).sort()
})
