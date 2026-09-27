import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AuthState {
  token: string | null
  username: string | null
  isPrivilegedMode: boolean
  setAuth: (token: string, username: string) => void
  setPrivilegedMode: (isPrivilegedMode: boolean) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      username: null,
      isPrivilegedMode: false,
      setAuth: (token, username) => set({ token, username }),
      setPrivilegedMode: (isPrivilegedMode) => set({ isPrivilegedMode }),
      logout: () => set({ token: null, username: null, isPrivilegedMode: false }),
    }),
    {
      name: 'codexj-auth',
      partialize: (state) => ({
        token: state.token,
        username: state.username,
        // Exclude isPrivilegedMode from persistence
      }),
    },
  ),
)
