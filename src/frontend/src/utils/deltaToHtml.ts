/**
 * Minimal Quill Delta → TipTap HTML converter for backwards-compatible loading of legacy entries.
 * Only needs to cover formats that CodexJ actually produced; not a full Delta spec implementation.
 */

type DeltaOp = {
  insert?: string | Record<string, unknown>
  attributes?: Record<string, unknown>
}

type Delta = { ops?: DeltaOp[] }

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function extractStr(value: unknown): string {
  if (typeof value === 'string') return value
  if (value && typeof value === 'object') {
    const v = value as Record<string, unknown>
    if (typeof v.src === 'string') return v.src
    if (typeof v.url === 'string') return v.url
  }
  return ''
}

function wrapInline(text: string, attrs: Record<string, unknown>): string {
  if (!text) return ''
  let html = escapeHtml(text)

  if (attrs.link) {
    const href = escapeHtml(String(attrs.link))
    html = `<a href="${href}">${html}</a>`
  }
  if (attrs.code) {
    html = `<code>${html}</code>`
  }
  if (attrs.bold) html = `<strong>${html}</strong>`
  if (attrs.italic) html = `<em>${html}</em>`
  if (attrs.underline) html = `<u>${html}</u>`
  if (attrs.strike) html = `<s>${html}</s>`

  return html
}

function openBlock(attrs: Record<string, unknown>): { open: string; close: string } {
  if (attrs.header === 1) return { open: '<h1>', close: '</h1>' }
  if (attrs.header === 2) return { open: '<h2>', close: '</h2>' }
  if (attrs.header === 3) return { open: '<h3>', close: '</h3>' }
  if (attrs.blockquote) return { open: '<blockquote><p>', close: '</p></blockquote>' }
  if (attrs['code-block']) return { open: '<pre><code>', close: '</code></pre>' }
  if (attrs.list === 'ordered') return { open: '<li>', close: '</li>' }
  if (attrs.list === 'bullet') return { open: '<li>', close: '</li>' }
  return { open: '<p>', close: '</p>' }
}

function renderEmbed(key: string, value: unknown): string {
  if (key === 'image') {
    const src = extractStr(value)
    return src ? `<img src="${escapeHtml(src)}">` : ''
  }
  if (key === 'video') {
    const src = extractStr(value)
    if (!src) return ''
    // Quill video is typically a YouTube iframe src
    return `<iframe src="${escapeHtml(src)}" frameborder="0" allowfullscreen="true"></iframe>`
  }
  if (key === 'audio') {
    if (typeof value === 'string') {
      return `<audio src="${escapeHtml(value)}" controls preload="metadata"></audio>`
    }
    if (value && typeof value === 'object') {
      const v = value as Record<string, unknown>
      const src = typeof v.src === 'string' ? v.src : typeof v.url === 'string' ? v.url : ''
      if (!src) return ''
      const filename = typeof v.original_filename === 'string' ? v.original_filename : ''
      const mediaId = typeof v.media_id === 'string' ? v.media_id : ''
      let attrs = `src="${escapeHtml(src)}" controls preload="metadata"`
      if (filename) attrs += ` data-original-filename="${escapeHtml(filename)}"`
      if (mediaId) attrs += ` data-media-id="${escapeHtml(mediaId)}"`
      return `<audio ${attrs}></audio>`
    }
    return ''
  }
  if (key === 'pdf') {
    const src = extractStr(value)
    return src ? `<div data-type="pdf" data-src="${escapeHtml(src)}"></div>` : ''
  }
  if (key === 'webpage') {
    if (!value || typeof value !== 'object') return ''
    const v = value as Record<string, unknown>
    const src = typeof v.src === 'string' ? v.src : ''
    const sourceUrl = typeof v.source_url === 'string' ? v.source_url : src
    const title = typeof v.title === 'string' ? v.title : ''
    const mediaId = typeof v.media_id === 'string' ? v.media_id : ''
    const status = v.status === 'pending' || v.status === 'failed' ? v.status : 'completed'
    const errorMessage = typeof v.error_message === 'string' ? v.error_message : ''
    let attrs = `data-type="webpage" data-src="${escapeHtml(src)}" data-source-url="${escapeHtml(sourceUrl)}" data-title="${escapeHtml(title)}" data-status="${status}" data-error-message="${escapeHtml(errorMessage)}"`
    if (mediaId) attrs += ` data-media-id="${escapeHtml(mediaId)}"`
    return `<div ${attrs}></div>`
  }
  return ''
}

export function deltaToHtml(body: unknown): string {
  if (typeof body === 'string') return body

  const delta = body as Delta
  if (!delta || !Array.isArray(delta.ops)) return ''

  const ops = delta.ops

  // We process ops left-to-right. Inline text is accumulated per line.
  // A `\n` op with block attributes terminates the current paragraph.
  // Block embeds (image, audio, etc.) are flushed as standalone elements.

  const parts: string[] = []
  // Buffer of inline HTML for the current paragraph
  let inlineBuffer = ''
  // Track list context for proper ol/ul wrapping
  let currentListType: 'ordered' | 'bullet' | null = null

  function flushList() {
    if (currentListType === null) return
    parts.push(currentListType === 'ordered' ? '</ol>' : '</ul>')
    currentListType = null
  }

  function ensureList(type: 'ordered' | 'bullet') {
    if (currentListType === type) return
    if (currentListType !== null) flushList()
    parts.push(type === 'ordered' ? '<ol>' : '<ul>')
    currentListType = type
  }

  function flushInlineAsBlock(blockAttrs: Record<string, unknown>) {
    const content = inlineBuffer
    inlineBuffer = ''
    const listType = blockAttrs.list === 'ordered' ? 'ordered' : blockAttrs.list === 'bullet' ? 'bullet' : null
    if (listType) {
      ensureList(listType)
    } else {
      flushList()
    }
    const { open, close } = openBlock(blockAttrs)
    // Empty paragraphs: Quill uses \n alone (no text) to denote a blank line
    parts.push(`${open}${content || (listType ? '' : '<br>')}${close}`)
  }

  for (const op of ops) {
    if (!op || typeof op !== 'object') continue

    const insert = op.insert
    const attrs = (op.attributes ?? {}) as Record<string, unknown>

    // Block embed (non-string insert)
    if (insert && typeof insert === 'object') {
      const embedKeys = ['image', 'video', 'audio', 'pdf', 'webpage']
      for (const key of embedKeys) {
        if (key in insert) {
          // Flush current inline paragraph before embed
          if (inlineBuffer) {
            flushList()
            parts.push(`<p>${inlineBuffer}</p>`)
            inlineBuffer = ''
          } else {
            // no-op
          }
          flushList()
          const embedHtml = renderEmbed(key, (insert as Record<string, unknown>)[key])
          if (embedHtml) parts.push(embedHtml)
          break
        }
      }
      continue
    }

    if (typeof insert !== 'string') continue

    // Text contains one or more newlines
    const segments = insert.split('\n')
    for (let i = 0; i < segments.length; i++) {
      const segment = segments[i]
      if (i < segments.length - 1) {
        // Each segment except the last ends with a newline
        inlineBuffer += wrapInline(segment, attrs)
        // The \n itself may carry block attributes — only the last op's attrs apply to the line
        // But in Delta format, the \n is part of this same op's text.
        // For simplicity treat each internal newline as a plain paragraph break.
        // The attributes of the whole insert op apply to the last \n only (Delta convention).
        const isLastNewline = (i === segments.length - 2)
        if (isLastNewline) {
          flushInlineAsBlock(attrs)
        } else {
          flushList()
          parts.push(`<p>${inlineBuffer || '<br>'}</p>`)
          inlineBuffer = ''
        }
      } else {
        // Last segment (no trailing newline) — accumulate
        inlineBuffer += wrapInline(segment, attrs)
      }
    }
  }

  // Flush any remaining inline content as a final paragraph
  if (inlineBuffer) {
    flushList()
    parts.push(`<p>${inlineBuffer}</p>`)
  }
  flushList()

  return parts.join('')
}
