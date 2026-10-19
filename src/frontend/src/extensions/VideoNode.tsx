import { Node, mergeAttributes } from '@tiptap/core'
import { NodeViewWrapper, ReactNodeViewRenderer } from '@tiptap/react'
import type { NodeViewProps } from '@tiptap/core'

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    video: {
      insertVideo: (attrs: { src: string }) => ReturnType
    }
  }
}

function VideoNodeView({ node }: NodeViewProps) {
  const src = node.attrs.src as string
  return (
    <NodeViewWrapper as="div" contentEditable={false} style={{ margin: '0.85rem 0' }}>
      <video
        src={src}
        controls
        style={{ maxWidth: '100%', borderRadius: '8px', display: 'block' }}
      />
    </NodeViewWrapper>
  )
}

export const VideoNode = Node.create({
  name: 'video',
  group: 'block',
  atom: true,
  draggable: true,

  addAttributes() {
    return {
      src: {
        default: null,
        parseHTML: (el) => el.getAttribute('src'),
        renderHTML: (attrs) => ({ src: attrs.src }),
      },
    }
  },

  parseHTML() {
    return [{ tag: 'video' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['video', mergeAttributes(HTMLAttributes, { controls: '' })]
  },

  addCommands() {
    return {
      insertVideo:
        (attrs) =>
        ({ commands }) =>
          commands.insertContent({ type: this.name, attrs }),
    }
  },

  addNodeView() {
    return ReactNodeViewRenderer(VideoNodeView)
  },
})
