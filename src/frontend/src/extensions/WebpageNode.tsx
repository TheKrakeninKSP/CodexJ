import { Node, mergeAttributes } from '@tiptap/core'
import { NodeViewWrapper, ReactNodeViewRenderer } from '@tiptap/react'
import type { NodeViewProps } from '@tiptap/core'
import { getWebpageSourceLabel } from '../utils/webpageEmbeds'

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    webpage: {
      insertWebpage: (attrs: WebpageNodeAttrs) => ReturnType
      updateWebpageByMediaId: (mediaId: string, attrs: Partial<WebpageNodeAttrs>) => ReturnType
    }
  }
}

export interface WebpageNodeAttrs {
  src: string
  sourceUrl: string
  title: string
  status?: 'pending' | 'completed' | 'failed'
  errorMessage?: string | null
  mediaId?: string | null
}

function hasLiveSourceUrl(url: string): boolean {
  return /^https?:\/\//i.test(url.trim())
}

function WebpageNodeView({ node }: NodeViewProps) {
  const attrs = node.attrs as WebpageNodeAttrs
  const status = attrs.status ?? 'completed'
  const isPending = status === 'pending'
  const isFailed = status === 'failed'
  const displayTitle = isPending
    ? 'Archiving webpage…'
    : attrs.title || getWebpageSourceLabel(attrs.sourceUrl)

  const cardStyle: React.CSSProperties = {
    display: 'flex', alignItems: 'center', gap: '0.65rem',
    padding: '0.6rem 0.85rem',
    border: `1px ${isPending ? 'dashed' : 'solid'} ${isFailed ? 'color-mix(in srgb, var(--danger) 55%, var(--border))' : 'var(--border)'}`,
    borderRadius: '10px',
    background: isFailed
      ? 'color-mix(in srgb, var(--danger) 10%, transparent)'
      : 'color-mix(in srgb, var(--bg-sidebar) 60%, transparent)',
    margin: '0.85rem 0',
    cursor: 'default',
    userSelect: 'none',
  }

  return (
    <NodeViewWrapper
      as="div"
      data-type="webpage"
      data-src={attrs.src}
      data-source-url={attrs.sourceUrl}
      data-title={attrs.title}
      data-status={status}
      data-error-message={attrs.errorMessage ?? ''}
      data-media-id={attrs.mediaId ?? undefined}
      contentEditable={false}
      style={cardStyle}
    >
      <span style={{ fontSize: '1.25rem', flexShrink: 0 }}>🌐︎</span>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{
          fontFamily: 'var(--font-ui)', fontSize: '0.88rem', fontWeight: 600,
          color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>
          {displayTitle}
        </div>
        <div style={{
          fontFamily: 'var(--font-ui)', fontSize: '0.75rem', color: 'var(--text-muted)',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>
          {getWebpageSourceLabel(attrs.sourceUrl)}
        </div>
        {(isPending || isFailed) && (
          <div style={{
            marginTop: '0.18rem', fontFamily: 'var(--font-ui)', fontSize: '0.72rem',
            color: isFailed ? 'var(--danger)' : 'var(--text-muted)',
          }}>
            {isPending ? 'Archiving in background' : (attrs.errorMessage || 'Archive failed')}
          </div>
        )}
      </div>
      {(hasLiveSourceUrl(attrs.sourceUrl) || (status === 'completed' && attrs.src)) && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem', flexShrink: 0 }}>
          {hasLiveSourceUrl(attrs.sourceUrl) && (
            <a
              href={attrs.sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              style={{
                fontFamily: 'var(--font-ui)', fontSize: '0.72rem', fontWeight: 500,
                color: 'var(--accent)', textDecoration: 'none', whiteSpace: 'nowrap',
                padding: '0.2rem 0.5rem', border: '1px solid var(--accent)',
                borderRadius: '5px', lineHeight: 1.4,
              }}
            >
              Open live site
            </a>
          )}
          {status === 'completed' && attrs.src && (
            <a
              href={attrs.src}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              style={{
                fontFamily: 'var(--font-ui)', fontSize: '0.72rem', fontWeight: 500,
                color: 'var(--text-muted)', textDecoration: 'none', whiteSpace: 'nowrap',
                padding: '0.2rem 0.5rem', border: '1px solid var(--border)',
                borderRadius: '5px', lineHeight: 1.4,
              }}
            >
              View archived
            </a>
          )}
        </div>
      )}
    </NodeViewWrapper>
  )
}

export const WebpageNode = Node.create({
  name: 'webpage',
  group: 'block',
  atom: true,
  draggable: true,

  addAttributes() {
    return {
      src: {
        default: '',
        parseHTML: (el) => el.getAttribute('data-src') ?? '',
        renderHTML: (attrs) => ({ 'data-src': attrs.src ?? '' }),
      },
      sourceUrl: {
        default: '',
        parseHTML: (el) => el.getAttribute('data-source-url') ?? '',
        renderHTML: (attrs) => ({ 'data-source-url': attrs.sourceUrl ?? '' }),
      },
      title: {
        default: '',
        parseHTML: (el) => el.getAttribute('data-title') ?? '',
        renderHTML: (attrs) => ({ 'data-title': attrs.title ?? '' }),
      },
      status: {
        default: 'completed',
        parseHTML: (el) => el.getAttribute('data-status') ?? 'completed',
        renderHTML: (attrs) => ({ 'data-status': attrs.status ?? 'completed' }),
      },
      errorMessage: {
        default: null,
        parseHTML: (el) => el.getAttribute('data-error-message') || null,
        renderHTML: (attrs) => ({ 'data-error-message': attrs.errorMessage ?? '' }),
      },
      mediaId: {
        default: null,
        parseHTML: (el) => el.getAttribute('data-media-id') || null,
        renderHTML: (attrs) => attrs.mediaId ? { 'data-media-id': attrs.mediaId } : {},
      },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-type="webpage"]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes, { 'data-type': 'webpage' })]
  },

  addCommands() {
    return {
      insertWebpage:
        (attrs) =>
        ({ commands }) =>
          commands.insertContent({ type: this.name, attrs }),

      updateWebpageByMediaId:
        (mediaId, updatedAttrs) =>
        ({ tr, dispatch, state }) => {
          let found = false
          state.doc.descendants((node, pos) => {
            if (node.type.name === 'webpage' && node.attrs.mediaId === mediaId) {
              found = true
              tr.setNodeMarkup(pos, undefined, { ...node.attrs, ...updatedAttrs })
            }
          })
          if (found && dispatch) dispatch(tr)
          return found
        },
    }
  },

  addNodeView() {
    return ReactNodeViewRenderer(WebpageNodeView)
  },
})

export function hasLiveWebpageUrl(sourceUrl: string): boolean {
  return hasLiveSourceUrl(sourceUrl)
}
