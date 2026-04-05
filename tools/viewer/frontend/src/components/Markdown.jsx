/** @module components/Markdown — Renders markdown content (fork-local) */

import { renderMarkdown } from '../utils/markdown.js'

export function Markdown({ text }) {
  if (!text) return null
  const html = renderMarkdown(text)
  return <div class="message-content" dangerouslySetInnerHTML={{ __html: html }} />
}
