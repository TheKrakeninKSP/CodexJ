import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { useWorkspaceStore } from '../stores/workspaceStore'
import {
  workspacesApi,
  journalsApi,
  dataManagementApi,
  authApi,
  type Workspace,
  type Journal,
} from '../services/api'
import styles from './Sidebar.module.css'

export default function Sidebar() {
  const navigate = useNavigate()
  const logout = useAuthStore((s) => s.logout)
  const username = useAuthStore((s) => s.username)
  const {
    workspaces, setWorkspaces,
    activeWorkspace, setActiveWorkspace,
    activeJournal, setActiveJournal,
  } = useWorkspaceStore()

  const [journals, setJournals] = useState<Journal[]>([])
  const [newWsName, setNewWsName] = useState('')
  const [newJName, setNewJName] = useState('')
  const [expandedWs, setExpandedWs] = useState<string | null>(null)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [encryptionKey, setEncryptionKey] = useState('')
  const [exporting, setExporting] = useState(false)
  const [deleteError, setDeleteError] = useState('')

  useEffect(() => {
    workspacesApi.list().then((r) => {
      setWorkspaces(r.data)
      if (!activeWorkspace && r.data.length > 0) {
        setActiveWorkspace(r.data[0])
        setExpandedWs(r.data[0].id)
      }
    })
  }, [])

  useEffect(() => {
    if (activeWorkspace) {
      journalsApi.list(activeWorkspace.id).then((r) => setJournals(r.data))
    }
  }, [activeWorkspace])

  const handleWsClick = (ws: Workspace) => {
    setActiveWorkspace(ws)
    setExpandedWs(expandedWs === ws.id ? null : ws.id)
    journalsApi.list(ws.id).then((r) => setJournals(r.data))
    navigate('/')
  }

  const handleJournalClick = (j: Journal) => {
    setActiveJournal(j)
    navigate(`/journals/${j.id}`)
  }

  const addWorkspace = async () => {
    if (!newWsName.trim()) return
    const r = await workspacesApi.create(newWsName.trim())
    setWorkspaces([...workspaces, r.data])
    setActiveWorkspace(r.data)
    setExpandedWs(r.data.id)
    setNewWsName('')
  }

  const addJournal = async () => {
    if (!activeWorkspace || !newJName.trim()) return
    const r = await journalsApi.create(activeWorkspace.id, newJName.trim())
    setJournals([...journals, r.data])
    setActiveJournal(r.data)
    setNewJName('')
    navigate(`/journals/${r.data.id}`)
  }

  const handleLogout = () => {
    logout()
    useWorkspaceStore.getState().reset()
    navigate('/login')
  }

  const handleExportAndDelete = async () => {
    if (!encryptionKey.trim() || encryptionKey.length < 8) {
      setDeleteError('Encryption key must be at least 8 characters')
      return
    }

    setExporting(true)
    setDeleteError('')

    try {
      // Step 1: Export data
      const exportRes = await dataManagementApi.export(encryptionKey)

      // Step 2: Download the dump file
      const downloadRes = await dataManagementApi.download(exportRes.data.filename)
      const blob = new Blob([downloadRes.data], { type: 'application/octet-stream' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = exportRes.data.filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)

      // Step 3: Delete user account
      await authApi.delete()

      // Step 4: Logout and redirect
      logout()
      useWorkspaceStore.getState().reset()
      navigate('/login')
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Export failed'
      setDeleteError(msg)
    } finally {
      setExporting(false)
    }
  }

  return (
    <aside className={styles.sidebar}>
      <div className={styles.brand}>CodexJ</div>
      <div className={styles.user}>✦ {username}</div>

      <div className={styles.section}>
        <p className={styles.sectionLabel}>Workspaces</p>
        {workspaces.map((ws) => (
          <div key={ws.id}>
            <button
              className={`${styles.treeItem} ${activeWorkspace?.id === ws.id ? styles.active : ''}`}
              onClick={() => handleWsClick(ws)}
            >
              {ws.name}
            </button>
            {expandedWs === ws.id && (
              <div className={styles.journals}>
                {journals.map((j) => (
                  <button
                    key={j.id}
                    className={`${styles.journalItem} ${activeJournal?.id === j.id ? styles.active : ''}`}
                    onClick={() => handleJournalClick(j)}
                  >
                    {j.name}
                  </button>
                ))}
                <div className={styles.addRow}>
                  <input
                    className={`input ${styles.miniInput}`}
                    placeholder="New journal…"
                    value={newJName}
                    onChange={(e) => setNewJName(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && addJournal()}
                  />
                  <button className="btn" onClick={addJournal}>+</button>
                </div>
              </div>
            )}
          </div>
        ))}
        <div className={styles.addRow}>
          <input
            className={`input ${styles.miniInput}`}
            placeholder="New workspace…"
            value={newWsName}
            onChange={(e) => setNewWsName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addWorkspace()}
          />
          <button className="btn" onClick={addWorkspace}>+</button>
        </div>
      </div>

      <div className={styles.bottom}>
        {!showDeleteConfirm ? (
          <>
            <button
              className="btn btn-ghost"
              style={{ marginBottom: '0.5rem', width: '100%' }}
              onClick={() => setShowDeleteConfirm(true)}
            >
              Export & Delete Account
            </button>
            <button className="btn btn-ghost" onClick={handleLogout}>
              Log out
            </button>
          </>
        ) : (
          <div className={styles.deleteConfirm}>
            <p className={styles.deleteWarning}>
              This will export your data and permanently delete your account.
            </p>
            <input
              className="input"
              type="password"
              placeholder="Encryption key (min 8 chars)"
              value={encryptionKey}
              onChange={(e) => setEncryptionKey(e.target.value)}
              style={{ marginBottom: '0.5rem' }}
            />
            {deleteError && <p className="error-text">{deleteError}</p>}
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button
                className="btn btn-danger"
                onClick={handleExportAndDelete}
                disabled={exporting}
              >
                {exporting ? 'Exporting...' : 'Confirm Delete'}
              </button>
              <button
                className="btn btn-ghost"
                onClick={() => {
                  setShowDeleteConfirm(false)
                  setEncryptionKey('')
                  setDeleteError('')
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </aside>
  )
}
