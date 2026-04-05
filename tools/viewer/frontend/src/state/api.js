/** @module state/api — API client for Forensic Viewer backend (fork-local) */

const BASE = ''  // Vite proxy handles /api → FastAPI

// ── Sessions ───────────────────────────────
export async function fetchSessions() {
  const res = await fetch(`${BASE}/api/sessions`)
  if (!res.ok) throw new Error(`Sessions: ${res.status}`)
  return res.json()
}

export async function fetchSessionDetail(filename, page, limit) {
  let url = `${BASE}/api/sessions/${filename}`
  const params = new URLSearchParams()
  if (page != null) params.set('page', page)
  if (limit != null) params.set('limit', limit)
  const qs = params.toString()
  if (qs) url += `?${qs}`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Session detail: ${res.status}`)
  return res.json()
}

export async function deleteSession(filename) {
  const res = await fetch(`${BASE}/api/sessions/${filename}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`Delete session: ${res.status}`)
  return res.json()
}

export async function deleteMessages(filename, indices) {
  const res = await fetch(`${BASE}/api/sessions/${filename}/messages`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ indices }),
  })
  if (!res.ok) throw new Error(`Delete messages: ${res.status}`)
  return res.json()
}

// ── Subagents ──────────────────────────────
export async function fetchSubagents(agent) {
  let url = `${BASE}/api/subagents`
  if (agent) url += `?agent=${encodeURIComponent(agent)}`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Subagents: ${res.status}`)
  return res.json()
}

export async function fetchSubagentDetail(filename) {
  const res = await fetch(`${BASE}/api/subagents/${filename}`)
  if (!res.ok) throw new Error(`Subagent detail: ${res.status}`)
  return res.json()
}

// ── Memory ─────────────────────────────────
export async function fetchMemory(fileType, agent) {
  let url = `${BASE}/api/memory/${fileType}`
  if (agent) url += `?agent=${encodeURIComponent(agent)}`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Memory: ${res.status}`)
  return res.json()
}

export async function clearMemory(fileType, agent) {
  let url = `${BASE}/api/memory/${fileType}`
  if (agent) url += `?agent=${encodeURIComponent(agent)}`
  const res = await fetch(url, { method: 'DELETE' })
  if (!res.ok) throw new Error(`Clear memory: ${res.status}`)
  return res.json()
}

// ── Config ─────────────────────────────────
export async function fetchConfig(agent) {
  let url = `${BASE}/api/config-manager/`
  if (agent) url += `?agent=${encodeURIComponent(agent)}`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Config: ${res.status}`)
  return res.json()
}

export async function saveConfig(data, agent) {
  let url = `${BASE}/api/config-manager/`
  if (agent) url += `?agent=${encodeURIComponent(agent)}`
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`Save config: ${res.status}`)
  return res.json()
}

// ── System ─────────────────────────────────
export function getDeployStreamUrl() { return `${BASE}/api/system/deploy/stream` }
export function getRestartStreamUrl(agent) {
  let url = `${BASE}/api/system/restart/stream`
  if (agent) url += `?agent=${encodeURIComponent(agent)}`
  return url
}
export async function triggerRestart(agent) {
  let url = `${BASE}/api/system/restart`
  if (agent) url += `?agent=${encodeURIComponent(agent)}`
  const res = await fetch(url, { method: 'POST' })
  if (!res.ok) throw new Error(`Restart: ${res.status}`)
  return res.json()
}
export function getLogsStreamUrl(agent) {
  let url = `${BASE}/api/logs/stream`
  if (agent) url += `?agent=${encodeURIComponent(agent)}`
  return url
}
export function getSessionsWatchUrl() { return `${BASE}/api/sessions/watch` }
export function getSubagentsWatchUrl(agent) {
  let url = `${BASE}/api/subagents/watch`
  if (agent) url += `?agent=${encodeURIComponent(agent)}`
  return url
}
