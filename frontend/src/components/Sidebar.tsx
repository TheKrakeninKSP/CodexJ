import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { useWorkspaceStore } from '../stores/workspaceStore'
import {
  workspacesApi,
  journalsApi,
  dataManagementApi,
  mediaApi,
  authApi,
  type Journal,
  type Workspace,
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
    journals, setJournals,
  } = useWorkspaceStore()

  const [newWsName, setNewWsName] = useState('')
  const [newJName, setNewJName] = useState('')
  const [showNewWsInput, setShowNewWsInput] = useState(false)
  const [showNewJInput, setShowNewJInput] = useState(false)
  const workspaceInputRef = useRef<HTMLInputElement | null>(null)
  const journalInputRef = useRef<HTMLInputElement | null>(null)
  const [expandedWs, setExpandedWs] = useState<string | null>(null)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [encryptionKey, setEncryptionKey] = useState('')
  const [exporting, setExporting] = useState(false)
  const [trimmingMedia, setTrimmingMedia] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const [workspaceError, setWorkspaceError] = useState('')
  const [journalError, setJournalError] = useState('')

  const getApiErrorMessage = (err: unknown, fallback: string) => {
    const detail = (err as { response?: { data?: { detail?: unknown; message?: unknown } } })
      ?.response?.data?.detail
    const message = (err as { response?: { data?: { detail?: unknown; message?: unknown } } })
      ?.response?.data?.message

    if (typeof detail === 'string' && detail.trim()) return detail
    if (Array.isArray(detail)) {
      const text = detail
        .map((item) => {
          if (typeof item === 'string') return item
          if (item && typeof item === 'object' && 'msg' in item) {
            const msg = (item as { msg?: unknown }).msg
            return typeof msg === 'string' ? msg : ''
          }
          return ''
        })
        .filter(Boolean)
        .join(', ')
      if (text) return text
    }

    if (typeof message === 'string' && message.trim()) return message
    return fallback
  }

  useEffect(() => {
    workspacesApi.list().then((r) => {
      setWorkspaces(r.data)
      if (r.data.length === 0) return

      if (activeWorkspace) {
        const matchingWorkspace = r.data.find((ws) => ws.id === activeWorkspace.id)
        const workspaceToUse = matchingWorkspace ?? r.data[0]
        setActiveWorkspace(workspaceToUse)
        setExpandedWs(workspaceToUse.id)
        return
      }

      setActiveWorkspace(r.data[0])
      setExpandedWs(r.data[0].id)
    })
  }, [])

  useEffect(() => {
    if (activeWorkspace) {
      journalsApi.list(activeWorkspace.id).then((r) => setJournals(r.data))
      setShowNewJInput(false)
      setNewJName('')
    }
  }, [activeWorkspace])

  useEffect(() => {
    if (showNewWsInput) {
      workspaceInputRef.current?.focus()
    }
  }, [showNewWsInput])

  useEffect(() => {
    if (showNewJInput) {
      journalInputRef.current?.focus()
    }
  }, [showNewJInput])

  const handleWsClick = (ws: Workspace) => {
    console.log('Workspace clicked, navigating to /')
    setExpandedWs(ws.id)
    if (activeWorkspace?.id !== ws.id) {
      setActiveWorkspace(ws)  // useEffect will fetch journals when this changes
    }
    navigate('/')
  }

  const handleJournalClick = (j: Journal) => {
    setActiveJournal(j)
    navigate(`/journals/${j.id}`)
  }

  const addWorkspace = async () => {
    if (!newWsName.trim()) return
    setWorkspaceError('')
    try {
      const r = await workspacesApi.create(newWsName.trim())
      setWorkspaces([...workspaces, r.data])
      setActiveWorkspace(r.data)
      setExpandedWs(r.data.id)
      setNewWsName('')
      setShowNewWsInput(false)
    } catch (err: unknown) {
      setWorkspaceError(getApiErrorMessage(err, 'Could not create workspace.'))
    }
  }

  const addJournal = async () => {
    if (!activeWorkspace || !newJName.trim()) return
    setJournalError('')
    try {
      const r = await journalsApi.create(activeWorkspace.id, newJName.trim())
      setJournals([...journals, r.data])
      setActiveJournal(r.data)
      setNewJName('')
      setShowNewJInput(false)
      navigate(`/journals/${r.data.id}`)
    } catch (err: unknown) {
      setJournalError(getApiErrorMessage(err, 'Could not create journal.'))
    }
  }

  const handleWorkspacePlus = () => {
    if (!showNewWsInput) {
      setWorkspaceError('')
      setShowNewWsInput(true)
      return
    }
    void addWorkspace()
  }

  const handleJournalPlus = () => {
    if (!showNewJInput) {
      setJournalError('')
      setShowNewJInput(true)
      return
    }
    void addJournal()
  }

  const handleLogout = () => {
    logout()
    useWorkspaceStore.getState().reset()
    navigate('/login')
  }

  const downloadDumpFile = async (filename: string) => {
    const downloadRes = await dataManagementApi.download(filename)
    const blob = new Blob([downloadRes.data], { type: 'application/octet-stream' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
  }

  const handleExportOnly = async () => {
    const key = window.prompt('Enter encryption key (min 8 chars)')?.trim() ?? ''
    if (!key) return

    if (key.length < 8) {
      window.alert('Encryption key must be at least 8 characters')
      return
    }

    setExporting(true)
    try {
      const exportRes = await dataManagementApi.export(key)
      await downloadDumpFile(exportRes.data.filename)
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Export failed'
      window.alert(msg)
    } finally {
      setExporting(false)
    }
  }

  const handleTrimMedia = async () => {
    if (trimmingMedia) return

    setTrimmingMedia(true)
    try {
      const res = await mediaApi.trim()
      window.alert(`Trim complete. Removed ${res.data.deleted_count} of ${res.data.scanned_count} media files.`)
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Media trim failed'
      window.alert(msg)
    } finally {
      setTrimmingMedia(false)
    }
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
      await downloadDumpFile(exportRes.data.filename)

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
                  {showNewJInput && (
                    <input
                      ref={journalInputRef}
                      className={`input ${styles.miniInput}`}
                      placeholder="New journal..."
                      value={newJName}
                      onChange={(e) => {
                        setNewJName(e.target.value)
                        if (journalError) setJournalError('')
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          void addJournal()
                        }
                        if (e.key === 'Escape') {
                          setShowNewJInput(false)
                          setNewJName('')
                          setJournalError('')
                        }
                      }}
                    />
                  )}
                  <button className={`btn ${styles.plusButton}`} onClick={handleJournalPlus}>+</button>
                </div>
                {journalError && <p className="error-text">{journalError}</p>}
              </div>
            )}
          </div>
        ))}
        <div className={styles.addRow}>
          {showNewWsInput && (
            <input
              ref={workspaceInputRef}
              className={`input ${styles.miniInput}`}
              placeholder="New workspace..."
              value={newWsName}
              onChange={(e) => {
                setNewWsName(e.target.value)
                if (workspaceError) setWorkspaceError('')
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  void addWorkspace()
                }
                if (e.key === 'Escape') {
                  setShowNewWsInput(false)
                  setNewWsName('')
                  setWorkspaceError('')
                }
              }}
            />
          )}
          <button className={`btn ${styles.plusButton}`} onClick={handleWorkspacePlus}>+</button>
        </div>
        {workspaceError && <p className="error-text">{workspaceError}</p>}
      </div>

      <div className={styles.bottom}>
        {!showDeleteConfirm ? (
          <>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button className="btn btn-ghost" onClick={handleLogout}>
                Log out
              </button>
              <button className="btn btn-ghost" onClick={() => void handleExportOnly()} disabled={exporting}>
                {exporting ? 'Exporting...' : 'Export'}
              </button>
              <button className="btn btn-ghost" onClick={() => void handleTrimMedia()} disabled={trimmingMedia}>
                {trimmingMedia ? 'Trimming...' : 'Trim media'}
              </button>
              <button
                className="btn btn-ghost"
                onClick={() => setShowDeleteConfirm(true)}
              >
                Shred
              </button>
            </div>
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
