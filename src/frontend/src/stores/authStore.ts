import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AuthState {
  token: string | null
  username: string | null
  isPrivilegedMode: boolean
  /** From GET /auth/me; not persisted, re-fetched whenever the token changes. */
  isAdmin: boolean
  setAuth: (token: string, username: string) => void
  setPrivilegedMode: (isPrivilegedMode: boolean) => void
  setIsAdmin: (isAdmin: boolean) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      username: null,
      isPrivilegedMode: false,
      isAdmin: false,
      setAuth: (token, username) => set({ token, username }),
      setPrivilegedMode: (isPrivilegedMode) => set({ isPrivilegedMode }),
      setIsAdmin: (isAdmin) => set({ isAdmin }),
      logout: () => set({ token: null, username: null, isPrivilegedMode: false, isAdmin: false }),
    }),
    {
      name: 'codexj-auth',
      partialize: (state) => ({
        token: state.token,
        username: state.username,
        // Exclude isPrivilegedMode and isAdmin from persistence
      }),
    },
  ),
)
