import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AuthState {
  token: string | null
  username: string | null
  isPrivilegedMode: boolean
  setAuth: (token: string, username: string, isPrivilegedMode?: boolean) => void
  setPrivilegedMode: (isPrivilegedMode: boolean) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      username: null,
      isPrivilegedMode: false,
      setAuth: (token, username, isPrivilegedMode = false) =>
        set({ token, username, isPrivilegedMode }),
      setPrivilegedMode: (isPrivilegedMode) => set({ isPrivilegedMode }),
      logout: () => set({ token: null, username: null, isPrivilegedMode: false }),
    }),
    { name: 'codexj-auth' },
  ),
)
