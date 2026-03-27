import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './stores/authStore'
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
