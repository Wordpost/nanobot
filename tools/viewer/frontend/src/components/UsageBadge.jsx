import { formatTokens } from '../utils/format.js'
import { calculateCost, formatCost } from '../utils/costs.js'

export function UsageBadge({ usage, model }) {
  if (!usage) return null
  const total = usage.total_tokens || 0
  const cached = usage.cached_tokens || 0
  const reqs = usage.requests || 0
  const cachedPct = total ? Math.round((cached / total) * 100) : 0
  
  const cost = calculateCost(usage, model)
  const costStr = formatCost(cost)

  const title = `Prompt: ${formatTokens(usage.prompt_tokens)} | Completion: ${formatTokens(usage.completion_tokens)} | Cached: ${cachedPct}% | Estimated Cost: ${costStr}`

  return (
    <span class="usage-badge" title={title}>
      <svg width="11" height="11" viewBox="0 0 16 16" fill="currentColor"><circle cx="8" cy="8" r="7" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M8 4v5l3 2" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg>
      {formatTokens(total)}
      {cost > 0 && <span class="usage-cost">{costStr}</span>}
      {cached > 0 && <span class="usage-cached">⚡{cachedPct}%</span>}
      {reqs > 1 && <span class="usage-reqs">⟳{reqs}</span>}
    </span>
  )
}
