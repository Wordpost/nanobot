/** @module components/Toast — Notification system (fork-local) */

import { useState, useEffect } from 'preact/hooks'
import { signal } from '@preact/signals'

const toasts = signal([])
let _id = 0

export function showToast(message, type = 'info', duration = 4000) {
  const id = ++_id
  toasts.value = [...toasts.value, { id, message, type }]
  if (duration > 0) {
    setTimeout(() => dismissToast(id), duration)
  }
  return id
}

export function dismissToast(id) {
  toasts.value = toasts.value.filter(t => t.id !== id)
}

const ICONS = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' }

export function ToastContainer() {
  const list = toasts.value
  if (list.length === 0) return null

  return (
    <div class="toast-container">
      {list.map(t => (
        <div key={t.id} class={`toast ${t.type}`}>
          <span class="toast-icon">{ICONS[t.type] || 'ℹ️'}</span>
          <span>{t.message}</span>
          <button class="toast-close" onClick={() => dismissToast(t.id)}>✕</button>
        </div>
      ))}
    </div>
  )
}
