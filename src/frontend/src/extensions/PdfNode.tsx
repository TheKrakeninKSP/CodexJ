import { Node, mergeAttributes } from '@tiptap/core'
import { NodeViewWrapper, ReactNodeViewRenderer } from '@tiptap/react'
import type { NodeViewProps } from '@tiptap/core'

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    pdf: {
      insertPdf: (attrs: { src: string }) => ReturnType
    }
  }
}

function getFileName(src: string): string {
  try {
    const parts = new URL(src, window.location.origin).pathname.split('/')
    return decodeURIComponent(parts[parts.length - 1] || 'document.pdf')
  } catch {
    return 'document.pdf'
  }
}

function PdfNodeView({ node }: NodeViewProps) {
  const src = node.attrs.src as string
  return (
    <NodeViewWrapper as="div" data-type="pdf" data-src={src} contentEditable={false}
      style={{
        display: 'flex', alignItems: 'center', gap: '0.65rem',
        padding: '0.6rem 0.85rem', border: '1px solid var(--border)',
        borderRadius: '10px', background: 'color-mix(in srgb, var(--bg-sidebar) 60%, transparent)',
        margin: '0.85rem 0', cursor: 'default', userSelect: 'none',
      }}
    >
      <span style={{ fontSize: '1.25rem', flexShrink: 0 }}>📄</span>
      <span style={{
        fontFamily: 'var(--font-ui)', fontSize: '0.88rem', color: 'var(--text-primary)',
        flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
      }}>
        {getFileName(src)}
      </span>
      <a
        href={src} target="_blank" rel="noopener noreferrer"
        onClick={(e) => e.stopPropagation()}
        style={{
          fontFamily: 'var(--font-ui)', fontSize: '0.72rem', padding: '0.25rem 0.55rem',
          borderRadius: '6px', border: '1px solid var(--accent)', color: 'var(--accent)',
          background: 'transparent', textDecoration: 'none', whiteSpace: 'nowrap',
        }}
      >
        Open PDF
      </a>
    </NodeViewWrapper>
  )
}

export const PdfNode = Node.create({
  name: 'pdf',
  group: 'block',
  atom: true,
  draggable: true,

  addAttributes() {
    return {
      src: {
        default: null,
        parseHTML: (el) => el.getAttribute('data-src'),
        renderHTML: (attrs) => ({ 'data-src': attrs.src }),
      },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-type="pdf"]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes, { 'data-type': 'pdf' })]
  },

  addCommands() {
    return {
      insertPdf:
        (attrs) =>
        ({ commands }) =>
          commands.insertContent({ type: this.name, attrs }),
    }
  },

  addNodeView() {
    return ReactNodeViewRenderer(PdfNodeView)
  },
})
