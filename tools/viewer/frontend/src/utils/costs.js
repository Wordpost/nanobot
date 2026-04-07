/** @module utils/costs — Cost calculation for LLM tokens (fork-local) */

/**
 * Simplified pricing map for common models.
 * Rates per 1M tokens in USD.
 * [Input, Output]
 */
const PRICING = {
  // OpenAI
  'gpt-4o': [5.0, 15.0],
  'gpt-4o-mini': [0.15, 0.6],
  'gpt-4-turbo': [10.0, 30.0],
  'o1-preview': [15.0, 60.0],
  'o1-mini': [3.0, 12.0],

  // Anthropic
  'claude-3-5-sonnet': [3.0, 15.0],
  'claude-3-5-sonnet-20240620': [3.0, 15.0],
  'claude-3-5-sonnet-20241022': [3.0, 15.0],
  'claude-3-opus': [15.0, 75.0],
  'claude-3-haiku': [0.25, 1.25],

  // DeepSeek
  'deepseek-chat': [1.0, 2.0],
  'deepseek-reasoner': [1.0, 2.0],
  'deepseek-v3': [0.14, 0.28], // roughly

  // Default / Unknown (Cheap fallback)
  'default': [1.0, 2.0]
}

/**
 * Calculates estimated cost for usage.
 * @param {object} usage - Usage object from provider
 * @param {string} model - Model name slug
 * @returns {number} Estimated cost in USD
 */
export function calculateCost(usage, model = '') {
  if (!usage) return 0
  
  const slug = (model || '').toLowerCase()
  let [rateIn, rateOut] = PRICING['default']

  // Try to find matching rate
  for (const [key, rates] of Object.entries(PRICING)) {
    if (slug.includes(key)) {
      [rateIn, rateOut] = rates
      break
    }
  }

  const promptCost = ((usage.prompt_tokens || 0) / 1_000_000) * rateIn
  const completionCost = ((usage.completion_tokens || 0) / 1_000_000) * rateOut
  
  return promptCost + completionCost
}

/**
 * Formats cost for display.
 * @param {number} cost - Cost in USD
 * @returns {string} Formatted string
 */
export function formatCost(cost) {
  if (cost === 0) return '$0.00'
  if (cost < 0.001) return `<$0.001`
  return `$${cost.toFixed(3)}`
}
