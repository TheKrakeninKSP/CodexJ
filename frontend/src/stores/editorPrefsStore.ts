import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type ContentWidth = 'narrow' | 'medium' | 'wide' | 'full'

export const CONTENT_WIDTH_MAP: Record<ContentWidth, string> = {
  narrow: '600px',
  medium: '800px',
  wide: '1100px',
  full: '100%',
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
      contentWidth: 'medium',
      stickyToolbar: false,
      setContentWidth: (w) => set({ contentWidth: w }),
      setStickyToolbar: (v) => set({ stickyToolbar: v }),
    }),
    { name: 'codexj-editor-prefs' },
  ),
)
