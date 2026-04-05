/** @module utils/markdown — Line-by-line markdown renderer (fork-local)
 *  Migrated from legacy ui.js renderMarkdown().
 *  Returns HTML string — use with dangerouslySetInnerHTML.
 */

import { escapeHtml } from './format.js'

export function renderMarkdown(text) {
  if (!text) return ''

  const lines = text.split('\n')
  let html = ''
  let inCodeBlock = false
  let codeLang = ''
  let codeLines = []
  let inTable = false
  let tableRows = []
  let listType = null
  let listItems = []

  function flushList() {
    if (listItems.length === 0) return ''
    const tag = listType === 'ol' ? 'ol' : 'ul'
    const out = `<${tag} class="md-list">${listItems.join('')}</${tag}>`
    listItems = []
    listType = null
    return out
  }

  function flushTable() {
    if (tableRows.length === 0) return ''
    let out = '<div class="md-table-wrapper"><table class="md-table"><thead><tr>'
    const headers = tableRows[0]
    headers.forEach(h => { out += `<th>${escapeHtml(h.trim())}</th>` })
    out += '</tr></thead><tbody>'
    for (let i = 2; i < tableRows.length; i++) {
      out += '<tr>'
      tableRows[i].forEach(c => { out += `<td>${inlineMarkdown(c.trim())}</td>` })
      out += '</tr>'
    }
    out += '</tbody></table></div>'
    tableRows = []
    inTable = false
    return out
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]

    // Code blocks
    if (line.trimStart().startsWith('```')) {
      if (inCodeBlock) {
        const code = escapeHtml(codeLines.join('\n'))
        const header = codeLang
          ? `<div class="code-block-header"><span>${escapeHtml(codeLang)}</span><button class="btn-copy" onclick="navigator.clipboard.writeText(this.closest('.code-block-wrapper').querySelector('pre').textContent).then(()=>{this.textContent='✓';setTimeout(()=>this.textContent='Copy',1500)})">Copy</button></div>`
          : ''
        html += `<div class="code-block-wrapper">${header}<pre class="code-block">${code}</pre></div>`
        inCodeBlock = false
        codeLines = []
        codeLang = ''
      } else {
        html += flushList()
        html += flushTable()
        inCodeBlock = true
        codeLang = line.trimStart().slice(3).trim()
      }
      continue
    }
    if (inCodeBlock) { codeLines.push(line); continue }

    // Tables
    if (line.includes('|') && line.trim().startsWith('|')) {
      const cells = line.split('|').slice(1, -1)
      if (!inTable) {
        html += flushList()
        inTable = true
        tableRows = [cells]
      } else {
        if (cells.every(c => /^[\s:-]+$/.test(c))) {
          tableRows.push(cells) // separator row
        } else {
          tableRows.push(cells)
        }
      }
      continue
    }
    if (inTable) { html += flushTable() }

    // Empty line
    if (line.trim() === '') {
      html += flushList()
      html += '<div class="md-spacer"></div>'
      continue
    }

    // Headings
    const headingMatch = line.match(/^(#{1,6})\s+(.+)/)
    if (headingMatch) {
      html += flushList()
      const level = headingMatch[1].length
      html += `<div class="md-h${level}">${inlineMarkdown(headingMatch[2])}</div>`
      continue
    }

    // HR
    if (/^[-*_]{3,}\s*$/.test(line.trim())) {
      html += flushList()
      html += '<hr class="md-hr">'
      continue
    }

    // Lists
    const ulMatch = line.match(/^(\s*)[-*+]\s+(.+)/)
    const olMatch = line.match(/^(\s*)\d+\.\s+(.+)/)
    if (ulMatch) {
      if (listType !== 'ul') { html += flushList(); listType = 'ul' }
      listItems.push(`<li>${inlineMarkdown(ulMatch[2])}</li>`)
      continue
    }
    if (olMatch) {
      if (listType !== 'ol') { html += flushList(); listType = 'ol' }
      listItems.push(`<li>${inlineMarkdown(olMatch[2])}</li>`)
      continue
    }

    // Blockquote
    if (line.trimStart().startsWith('>')) {
      html += flushList()
      const content = line.replace(/^>\s?/, '')
      html += `<div style="border-left:2px solid var(--border-default);padding-left:12px;color:var(--text-secondary);margin:4px 0;">${inlineMarkdown(content)}</div>`
      continue
    }

    // Normal paragraph
    html += flushList()
    html += `<div>${inlineMarkdown(line)}</div>`
  }

  // Flush remaining
  if (inCodeBlock) {
    html += `<pre class="code-block">${escapeHtml(codeLines.join('\n'))}</pre>`
  }
  html += flushList()
  html += flushTable()

  return html
}

/** Inline markdown: bold, italic, code, links, strikethrough */
function inlineMarkdown(text) {
  let s = escapeHtml(text)
  // Bold
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  s = s.replace(/__(.+?)__/g, '<strong>$1</strong>')
  // Italic
  s = s.replace(/\*(.+?)\*/g, '<em>$1</em>')
  s = s.replace(/_(.+?)_/g, '<em>$1</em>')
  // Strikethrough
  s = s.replace(/~~(.+?)~~/g, '<del>$1</del>')
  // Code
  s = s.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')
  // Links
  s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
  // Auto-links
  s = s.replace(/(^|[^"=])(https?:\/\/[^\s<]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>')
  return s
}
