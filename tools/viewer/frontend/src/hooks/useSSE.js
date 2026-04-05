/** @module hooks/useSSE — SSE stream management hook (fork-local) */

import { useEffect, useRef, useState } from 'preact/hooks'
import { sseStatus } from '../state/signals.js'

/**
 * Custom hook for Server-Sent Events with auto-reconnect.
 * @param {string} url - SSE endpoint URL
 * @param {object} opts
 * @param {function} opts.onMessage - callback(data: any)
 * @param {function} [opts.onError] - callback(error)
 * @param {boolean} [opts.enabled=true] - toggle connection
 * @returns {{ status: string, error: string|null }}
 */
export function useSSE(url, { onMessage, onError, enabled = true } = {}) {
  const [status, setStatus] = useState('connecting') // 'connecting', 'connected', 'error'
  const [error, setError] = useState(null)
  const esRef = useRef(null)
  const retriesRef = useRef(0)
  const timerRef = useRef(null)
  const onMessageRef = useRef(onMessage)
  const onErrorRef = useRef(onError)

  // Keep callback refs fresh without re-triggering effect
  onMessageRef.current = onMessage
  onErrorRef.current = onError

  useEffect(() => {
    if (!enabled || !url) return

    function connect() {
      if (esRef.current) {
        esRef.current.close()
      }

      setStatus('connecting')
      sseStatus.value = 'connecting'
      
      const es = new EventSource(url)
      esRef.current = es

      es.onopen = () => {
        setStatus('connected')
        sseStatus.value = 'connected'
        setError(null)
        retriesRef.current = 0
      }

      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data)
          onMessageRef.current?.(data)
        } catch {
          // keepalive or non-JSON — ignore
        }
      }

      es.onerror = () => {
        setStatus('error')
        sseStatus.value = 'error'
        es.close()
        esRef.current = null

        // Exponential backoff: 1s → 2s → 4s → 8s → max 30s
        const delay = Math.min(1000 * Math.pow(2, retriesRef.current), 30000)
        retriesRef.current++
        setError('Connection lost')
        onErrorRef.current?.('Connection lost')

        timerRef.current = setTimeout(connect, delay)
      }
    }

    connect()

    return () => {
      if (esRef.current) {
        esRef.current.close()
        esRef.current = null
      }
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
      setStatus('disconnected')
      sseStatus.value = 'disconnected'
    }
  }, [url, enabled])

  return { status, error }
}

