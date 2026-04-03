import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { authApi } from './services/api'
import { applyTheme, normalizeThemeName } from './theme'
import { useAuthStore } from './stores/authStore'
import { useThemeStore } from './stores/themeStore'
import Login from './pages/Login'
import Register from './pages/Register'
import WorkspaceOverview from './pages/WorkspaceOverview'
import JournalView from './pages/JournalView'
import EntryReader from './pages/EntryReader'
import EntryEditor from './pages/EntryEditor'
import Help from './pages/Help'
import AppLayout from './components/AppLayout'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  return token ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  const token = useAuthStore((s) => s.token)
  const theme = useThemeStore((s) => s.theme)
  const setTheme = useThemeStore((s) => s.setTheme)

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.altKey && e.key === 'Enter') {
        e.preventDefault()
        const pywebview = (window as any).pywebview
        if (pywebview?.api?.toggle_fullscreen) {
          pywebview.api.toggle_fullscreen()
        } else if (document.fullscreenElement) {
          document.exitFullscreen()
        } else {
          document.documentElement.requestFullscreen()
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  useEffect(() => {
    if (!token) return

    let isActive = true
    authApi.getPreferences()
      .then((response) => {
        if (!isActive) return
        setTheme(normalizeThemeName(response.data.theme))
      })
      .catch(() => undefined)

    return () => {
      isActive = false
    }
  }, [token, setTheme])

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route
          element={
            <RequireAuth>
              <AppLayout />
            </RequireAuth>
          }
        >
          <Route path="/" element={<WorkspaceOverview />} />
          <Route path="/help" element={<Help />} />
          <Route path="/journals/:journalId" element={<JournalView />} />
          <Route path="/entries/new" element={<EntryEditor />} />
          <Route path="/entries/:entryId" element={<EntryReader />} />
          <Route path="/entries/:entryId/edit" element={<EntryEditor />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
