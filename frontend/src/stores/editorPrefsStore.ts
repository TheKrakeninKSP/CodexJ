import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type ContentWidth = 'Narrow' | 'Medium' | 'Wide' | 'Full'

export const CONTENT_WIDTH_MAP: Record<ContentWidth, string> = {
  Narrow: '600px',
  Medium: '800px',
  Wide: '1100px',
  Full: '100%',
}

interface EditorPrefsState {
  contentWidth: ContentWidth
  stickyToolbar: boolean
  setContentWidth: (w: ContentWidth) => void
  setStickyToolbar: (v: boolean) => void
}

export const useEditorPrefsStore = create<EditorPrefsState>()(
  persist(
    (set) => ({
      contentWidth: 'Medium',
      stickyToolbar: false,
      setContentWidth: (w) => set({ contentWidth: w }),
      setStickyToolbar: (v) => set({ stickyToolbar: v }),
    }),
    { name: 'codexj-editor-prefs' },
  ),
)
