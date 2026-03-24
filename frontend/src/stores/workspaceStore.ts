import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Workspace, Journal } from '../services/api'

interface WorkspaceState {
  workspaces: Workspace[]
  activeWorkspace: Workspace | null
  activeJournal: Journal | null
  journals: Journal[]
  setWorkspaces: (ws: Workspace[]) => void
  setActiveWorkspace: (ws: Workspace | null) => void
  setActiveJournal: (j: Journal | null) => void
  setJournals: (journals: Journal[]) => void
  reset: () => void
}

export const useWorkspaceStore = create<WorkspaceState>()(
  persist(
    (set) => ({
      workspaces: [],
      activeWorkspace: null,
      activeJournal: null,
      journals: [],
      setWorkspaces: (workspaces) => set({ workspaces }),
      setActiveWorkspace: (activeWorkspace) =>
        set({ activeWorkspace, activeJournal: null, journals: [] }),
      setActiveJournal: (activeJournal) => set({ activeJournal }),
      setJournals: (journals) => set({ journals }),
      reset: () =>
        set({ workspaces: [], activeWorkspace: null, activeJournal: null, journals: [] }),
    }),
    { name: 'codexj-workspace' }
  )
)
