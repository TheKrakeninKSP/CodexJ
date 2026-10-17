import { Node, mergeAttributes } from '@tiptap/core'

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    audio: {
      insertAudio: (attrs: {
        src: string
        originalFilename?: string | null
        mediaId?: string | null
      }) => ReturnType
    }
  }
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

  addCommands() {
    return {
      insertAudio:
        (attrs) =>
        ({ commands }) =>
          commands.insertContent({ type: this.name, attrs }),
    }
  },
})
