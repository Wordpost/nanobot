import { useEffect } from 'preact/hooks'
import { searchQuery, activeSession, filteredSessions } from '../state/signals.js'

export function useKeyboard() {
  useEffect(() => {
    function handleKeyDown(e) {
      // Focus search input on / or CMD+K / CTRL+K
      if (e.key === '/' || (e.key === 'k' && (e.metaKey || e.ctrlKey))) {
        e.preventDefault()
        document.getElementById('search-input')?.focus()
        return
      }

      // Navigate sessions with Arrow Up/Down
      if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
        const list = filteredSessions.value
        if (list.length === 0) return

        const currentIndex = list.findIndex(s => s.filename === activeSession.value)
        let nextIndex = currentIndex

        if (e.key === 'ArrowUp') {
          nextIndex = currentIndex > 0 ? currentIndex - 1 : list.length - 1
        } else {
          nextIndex = currentIndex < list.length - 1 ? currentIndex + 1 : 0
        }

        e.preventDefault()
        activeSession.value = list[nextIndex].filename
        
        // Scroll target into view
        const targetElement = document.querySelector(`[data-session-id="${list[nextIndex].filename}"]`)
        if (targetElement) {
          targetElement.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])
}
