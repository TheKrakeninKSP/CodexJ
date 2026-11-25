import { Node, mergeAttributes } from '@tiptap/core'

export type AudioDownloadStatus = 'pending' | 'failed'

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    audio: {
      insertAudio: (attrs: {
        src: string
        originalFilename?: string | null
        mediaId?: string | null
        downloadStatus?: AudioDownloadStatus | null
        downloadLabel?: string | null
      }) => ReturnType
      updateAudioDownload: (
        mediaId: string,
        attrs: { downloadStatus: AudioDownloadStatus | null; downloadError?: string | null },
      ) => ReturnType
    }
  }
}

/** Editor-only state for a song still being fetched by the server - never saved to HTML. */
const transient = { default: null, rendered: false, parseHTML: () => null }

function renderDownloadCard(attrs: Record<string, unknown>): HTMLElement {
  const failed = attrs.downloadStatus === 'failed'
  const card = document.createElement('div')
  card.contentEditable = 'false'
  card.setAttribute('data-audio-download', String(attrs.downloadStatus))
  Object.assign(card.style, {
    display: 'flex', alignItems: 'center', gap: '0.65rem',
    padding: '0.6rem 0.85rem', margin: '0.85rem 0', borderRadius: '10px',
    border: `1px ${failed ? 'solid' : 'dashed'} ${failed
      ? 'color-mix(in srgb, var(--danger) 55%, var(--border))' : 'var(--border)'}`,
    background: failed
      ? 'color-mix(in srgb, var(--danger) 10%, transparent)'
      : 'color-mix(in srgb, var(--bg-sidebar) 60%, transparent)',
    fontFamily: 'var(--font-ui)', userSelect: 'none',
  })

  const icon = document.createElement('span')
  icon.textContent = '♫'
  Object.assign(icon.style, { fontSize: '1.25rem', flexShrink: '0', color: 'var(--text-muted)' })

  const text = document.createElement('div')
  text.style.minWidth = '0'
  const title = document.createElement('div')
  title.textContent = String(attrs.downloadLabel || attrs.originalFilename || 'Song')
  Object.assign(title.style, {
    fontSize: '0.88rem', fontWeight: '600', color: 'var(--text-primary)',
    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
  })
  const status = document.createElement('div')
  status.textContent = failed
    ? String(attrs.downloadError || 'Download failed') + ' - delete this block and try again.'
    : 'Downloading audio from YouTube…'
  Object.assign(status.style, {
    fontSize: '0.75rem', color: failed ? 'var(--danger)' : 'var(--text-muted)',
  })
  text.append(title, status)
  card.append(icon, text)
  return card
}

export const AudioNode = Node.create({
  name: 'audio',
  group: 'block',
  atom: true,
  draggable: true,

  addAttributes() {
    return {
      src: { default: null },
      originalFilename: {
        default: null,
        parseHTML: (el) => el.getAttribute('data-original-filename'),
        renderHTML: (attrs) =>
          attrs.originalFilename ? { 'data-original-filename': attrs.originalFilename } : {},
      },
      mediaId: {
        default: null,
        parseHTML: (el) => el.getAttribute('data-media-id'),
        renderHTML: (attrs) =>
          attrs.mediaId ? { 'data-media-id': attrs.mediaId } : {},
      },
      downloadStatus: transient,
      downloadLabel: transient,
      downloadError: transient,
    }
  },

  parseHTML() {
    return [{ tag: 'audio[src]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return [
      'audio',
      mergeAttributes(HTMLAttributes, { controls: true, preload: 'metadata' }),
    ]
  },

  addNodeView() {
    return ({ node, HTMLAttributes }) => {
      if (node.attrs.downloadStatus) {
        return { dom: renderDownloadCard(node.attrs) }
      }
      // Same element renderHTML produces, so existing audio styling/hiding still applies.
      const audio = document.createElement('audio')
      const attrs = mergeAttributes(HTMLAttributes, { controls: true, preload: 'metadata' })
      for (const [key, value] of Object.entries(attrs)) {
        if (value === true) audio.setAttribute(key, '')
        else if (value != null && value !== false) audio.setAttribute(key, String(value))
      }
      return { dom: audio }
    }
  },

  addCommands() {
    return {
      insertAudio:
        (attrs) =>
        ({ commands }) =>
          commands.insertContent({ type: this.name, attrs }),

      updateAudioDownload:
        (mediaId, attrs) =>
        ({ tr, state, dispatch }) => {
          let found = false
          state.doc.descendants((node, pos) => {
            if (node.type.name === this.name && node.attrs.mediaId === mediaId) {
              found = true
              tr.setNodeMarkup(pos, undefined, { ...node.attrs, ...attrs })
            }
          })
          // Status bookkeeping, not an edit: keep it out of undo history.
          if (found && dispatch) dispatch(tr.setMeta('addToHistory', false))
          return found
        },
    }
  },
})
