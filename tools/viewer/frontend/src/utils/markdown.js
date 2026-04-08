/** @module utils/markdown — Markdown renderer using marked + highlight.js (fork-local)
 *  Returns HTML string — use with dangerouslySetInnerHTML.
 *  Replaces the legacy 168-line regex-based renderer.
 */

import { Marked } from 'marked'
import hljs from 'highlight.js/lib/core'

// Register only the languages we need (tree-shaking)
import json from 'highlight.js/lib/languages/json'
import python from 'highlight.js/lib/languages/python'
import javascript from 'highlight.js/lib/languages/javascript'
import typescript from 'highlight.js/lib/languages/typescript'
import yaml from 'highlight.js/lib/languages/yaml'
import bash from 'highlight.js/lib/languages/bash'
import css from 'highlight.js/lib/languages/css'
import xml from 'highlight.js/lib/languages/xml'
import markdown from 'highlight.js/lib/languages/markdown'
import diff from 'highlight.js/lib/languages/diff'

hljs.registerLanguage('json', json)
hljs.registerLanguage('python', python)
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('js', javascript)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('ts', typescript)
hljs.registerLanguage('yaml', yaml)
hljs.registerLanguage('yml', yaml)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('sh', bash)
hljs.registerLanguage('shell', bash)
hljs.registerLanguage('css', css)
hljs.registerLanguage('xml', xml)
hljs.registerLanguage('html', xml)
hljs.registerLanguage('markdown', markdown)
hljs.registerLanguage('md', markdown)
hljs.registerLanguage('diff', diff)

const marked = new Marked()

/** Escape HTML for safe insertion into attributes/text (fork-local) */
function escapeForAttr(str) {
  if (!str) return ''
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/**
 * Highlight code with hljs — by language or auto-detect.
 */
function highlightCode(code, lang) {
  if (lang && hljs.getLanguage(lang)) {
    try {
      return hljs.highlight(code, { language: lang, ignoreIllegals: true }).value
    } catch (_) { /* fallback */ }
  }
  try {
    return hljs.highlightAuto(code).value
  } catch (_) {
    return escapeForAttr(code)
  }
}

/**
 * Detects and strips line numbers from a text block (e.g. from read_file/exec).
 * Pattern: "1| content" or " 12| content"
 */
function preprocessFileContent(text) {
  if (!text) return ''
  const lines = text.split('\n')
  if (lines.length < 1) return text

  const lineNumPattern = /^\s*\d+\| /
  let matchCount = 0
  for (const line of lines) {
    if (lineNumPattern.test(line)) matchCount++
  }

  // If more than 50% lines follow the pattern, strip prefixes
  if (matchCount > lines.length * 0.5) {
    return lines.map(line => line.replace(lineNumPattern, '')).join('\n')
  }
  return text
}

// Custom renderer for code blocks with header + Copy button (fork-local)
const renderer = {
  code({ text, lang }) {
    const highlighted = highlightCode(text, lang)
    const langLabel = lang ? escapeForAttr(lang) : 'code'

    const copyBtnScript = `navigator.clipboard.writeText(this.closest('.code-block-wrapper').querySelector('pre').textContent).then(()=>{this.textContent='✓';setTimeout(()=>this.textContent='Copy',1500)})`

    return `
<div class="code-block-wrapper">
  <div class="code-block-header">
    <span>${langLabel}</span>
    <button class="btn-copy" onclick="${escapeForAttr(copyBtnScript)}">Copy</button>
  </div>
  <pre class="code-block"><code class="hljs">${highlighted}</code></pre>
</div>`.trim()
  }
}

marked.use({ renderer })

/**
 * Render markdown text to HTML string.
 * API-compatible with the legacy renderMarkdown().
 */
export function renderMarkdown(text) {
  if (!text) return ''
  
  // 1. Strip line numbers if it's a file dump
  const cleanText = preprocessFileContent(text)
  
  try {
    // 2. Parse synchronously
    return marked.parse(cleanText)
  } catch (err) {
    console.error('Markdown rendering error:', err)
    return `<pre class="fallback-pre">${escapeForAttr(text)}</pre>`
  }
}
