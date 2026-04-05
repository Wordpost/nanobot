import { useState, useEffect, useRef, useMemo, useCallback } from 'preact/hooks'

/**
 * Custom hook for virtual scrolling with dynamic item heights.
 * @param {object} options
 * @param {Array} options.items - The list of items to render
 * @param {number} [options.itemHeight=100] - Estimated height of an item
 * @param {object} options.containerRef - Ref to the scrollable container
 * @param {number} [options.overscan=5] - Number of items to render above and below the visible area
 */
export function useVirtualList({ items, itemHeight = 100, containerRef, overscan = 5 }) {
  const [scrollTop, setScrollTop] = useState(0)
  const [containerHeight, setContainerHeight] = useState(800)
  const itemHeights = useRef({})
  // ref to force re-calc if heights change significantly
  const [, setTick] = useState(0)
  const forceUpdate = useCallback(() => setTick(t => t + 1), [])

  // Monitor container scroll and resize
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    
    const handleScroll = () => {
      setScrollTop(container.scrollTop)
    }
    
    const observer = new ResizeObserver(entries => {
      for (const entry of entries) {
        setContainerHeight(entry.contentRect.height)
      }
    })
    
    container.addEventListener('scroll', handleScroll, { passive: true })
    observer.observe(container)
    
    setScrollTop(container.scrollTop)
    setContainerHeight(container.clientHeight)
    
    return () => {
      container.removeEventListener('scroll', handleScroll)
      observer.disconnect()
    }
  }, [containerRef])

  const setItemHeight = useCallback((index, height) => {
    if (Math.abs((itemHeights.current[index] || 0) - height) > 2) {
      itemHeights.current[index] = height
      // Debounce force update would be better, but for simplicity async update
      setTimeout(forceUpdate, 0)
    }
  }, [forceUpdate])

  // Calculate items to render
  const { startIndex, endIndex, totalHeight, offsetY } = useMemo(() => {
    if (!items || items.length === 0) {
      return { startIndex: 0, endIndex: -1, totalHeight: 0, offsetY: 0 }
    }

    let total = 0
    let start = 0
    
    // Find start index
    for (let i = 0; i < items.length; i++) {
      const h = itemHeights.current[i] || itemHeight
      if (total + h > scrollTop && start === 0) {
        start = i
      }
      total += h
    }
    
    let end = start
    let visibleHeight = 0
    while (end < items.length && visibleHeight < containerHeight) {
      visibleHeight += itemHeights.current[end] || itemHeight
      end++
    }
    
    start = Math.max(0, start - overscan)
    end = Math.min(items.length - 1, end + overscan)
    
    let offset = 0
    for(let i = 0; i < start; i++) {
      offset += itemHeights.current[i] || itemHeight
    }
    
    return { startIndex: start, endIndex: end, totalHeight: total, offsetY: offset }
  }, [items, scrollTop, containerHeight, overscan, itemHeight, /* tick dependency via useMemo */])

  const virtualItems = useMemo(() => {
    if (!items) return []
    return items.slice(startIndex, endIndex + 1).map((item, i) => {
      const originalIndex = startIndex + i
      return {
        item,
        index: originalIndex,
        // Using callback ref pattern
        measureRef: (el) => {
          if (el) {
            setItemHeight(originalIndex, el.getBoundingClientRect().height)
          }
        }
      }
    })
  }, [items, startIndex, endIndex, setItemHeight])

  return { virtualItems, totalHeight, offsetY }
}
