/** @module utils/format — Formatting helpers (fork-local) */

export function fixTimezone(isoStr) {
  if (!isoStr) return ''
  let str = String(isoStr)
  // If naive ISO 8601 (no Z and no time zone offset), assume it's UTC and append Z.
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(str)) {
    str += 'Z'
  }
  return str
}

export function formatDate(isoStr) {
  if (!isoStr) return ''
  try {
    const d = new Date(fixTimezone(isoStr))
    return d.toLocaleString('ru-RU', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch { return isoStr }
}

export function formatTime(isoStr) {
  if (!isoStr) return ''
  try {
    const d = new Date(fixTimezone(isoStr))
    return d.toLocaleTimeString('ru-RU')
  } catch { return isoStr }
}

export function formatSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
}

export function formatTokens(n) {
  if (!n) return '0'
  if (n < 1000) return String(n)
  return `${(n / 1000).toFixed(1)}k`
}

export function escapeHtml(str) {
  if (!str) return ''
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export function extractThinkBlocks(content) {
  if (!content) return { clean: '', thinks: [] }
  const thinks = []
  const clean = content.replace(/<think>([\s\S]*?)<\/think>/gi, (_, t) => {
    thinks.push(t.trim())
    return ''
  })
  return { clean: clean.trim(), thinks }
}
