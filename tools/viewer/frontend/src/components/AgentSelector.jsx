/** @module components/AgentSelector — Pool mode agent dropdown (fork-local) */

import { agentNames } from '../state/signals.js'

export function AgentSelector({ value, onChange }) {
  const agents = agentNames.value
  if (agents.length === 0) return null

  return (
    <div class="panel-agent-selector">
      <select
        class="agent-select"
        value={value || ''}
        onChange={e => onChange(e.target.value || null)}
      >
        <option value="">All Agents</option>
        {agents.map(a => <option key={a} value={a}>{a}</option>)}
      </select>
    </div>
  )
}
