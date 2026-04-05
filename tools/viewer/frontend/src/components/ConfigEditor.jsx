/** @module components/ConfigEditor — JSON config editor modal (fork-local) */

import { useState, useEffect } from 'preact/hooks'
import { activePanel, poolMode } from '../state/signals.js'
import { fetchConfig, saveConfig } from '../state/api.js'
import { AgentSelector } from './AgentSelector.jsx'
import { showToast } from './Toast.jsx'

export function ConfigEditor() {
  const [agent, setAgent] = useState(null)
  const [json, setJson] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchConfig(agent)
      .then(data => {
        if (data.message) {
          setJson('')
          setError(data.message)
        } else {
          setJson(JSON.stringify(data, null, 2))
        }
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [agent])

  async function handleSave() {
    try {
      const parsed = JSON.parse(json)
      await saveConfig(parsed, agent)
      showToast('Config saved', 'success')
    } catch (e) {
      showToast(`Save failed: ${e.message}`, 'error')
    }
  }

  return (
    <div class="bottom-panel" style="height:50vh">
      <div class="logs-header">
        <div style="display:flex;align-items:center;gap:8px">
          {poolMode.value && <AgentSelector value={agent} onChange={setAgent} />}
          <h3>⚙️ Config Editor</h3>
        </div>
        <div class="logs-actions">
          <button class="btn-sm" onClick={handleSave} disabled={loading || !!error}>💾 Save</button>
          <button class="btn-close-panel" onClick={() => activePanel.value = null}>✕</button>
        </div>
      </div>
      <div style="flex:1;overflow:hidden;display:flex;flex-direction:column">
        {loading && <div class="loading-state"><div class="spinner" /></div>}
        {error && (
          <div class="config-selection-required-container">
            <div class="config-selection-icon">⚙️</div>
            <div class="config-selection-required"><p>{error}</p></div>
          </div>
        )}
        {!loading && !error && (
          <textarea
            style="flex:1;width:100%;padding:16px 20px;background:var(--bg-primary);color:var(--text-primary);border:none;font-family:var(--font-mono);font-size:12px;line-height:1.6;resize:none;outline:none"
            value={json}
            onInput={e => setJson(e.target.value)}
            spellcheck={false}
          />
        )}
      </div>
    </div>
  )
}
