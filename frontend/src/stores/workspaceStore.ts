import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Workspace, Journal } from '../services/api'

interface WorkspaceState {
  workspaces: Workspace[]
  activeWorkspace: Workspace | null
  activeJournal: Journal | null
  setWorkspaces: (ws: Workspace[]) => void
  setActiveWorkspace: (ws: Workspace | null) => void
  setActiveJournal: (j: Journal | null) => void
  reset: () => void
}

export const useWorkspaceStore = create<WorkspaceState>()(
  persist(
    (set) => ({
      workspaces: [],
      activeWorkspace: null,
      activeJournal: null,
      setWorkspaces: (workspaces) => set({ workspaces }),
      setActiveWorkspace: (activeWorkspace) =>
        set({ activeWorkspace, activeJournal: null }),
      setActiveJournal: (activeJournal) => set({ activeJournal }),
      reset: () =>
        set({ workspaces: [], activeWorkspace: null, activeJournal: null }),
    }),
    { name: 'codexj-workspace' }
  )
)
