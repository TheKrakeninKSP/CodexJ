import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { useWorkspaceStore } from '../stores/workspaceStore'
import {
  workspacesApi,
  journalsApi,
  dataManagementApi,
  mediaApi,
  appApi,
  authApi,
  type Journal,
  type Workspace,
} from '../services/api'
import styles from './Sidebar.module.css'

export default function Sidebar() {
  const navigate = useNavigate()
  const logout = useAuthStore((s) => s.logout)
  const setAuth = useAuthStore((s) => s.setAuth)
  const username = useAuthStore((s) => s.username)
  const isPrivilegedMode = useAuthStore((s) => s.isPrivilegedMode)
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
  const [showExportConfirm, setShowExportConfirm] = useState(false)
  const [encryptionKey, setEncryptionKey] = useState('')
  const [exportKey, setExportKey] = useState('')
  const [exporting, setExporting] = useState(false)
  const [trimmingMedia, setTrimmingMedia] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const [exportError, setExportError] = useState('')
  const [workspaceError, setWorkspaceError] = useState('')
  const [journalError, setJournalError] = useState('')
  const [showPrivilegedPrompt, setShowPrivilegedPrompt] = useState(false)
  const [privilegedPassword, setPrivilegedPassword] = useState('')
  const [privilegedError, setPrivilegedError] = useState('')
  const [togglingPrivileged, setTogglingPrivileged] = useState(false)
  const [deletingWorkspaceId, setDeletingWorkspaceId] = useState<string | null>(null)
  const [deletingJournalId, setDeletingJournalId] = useState<string | null>(null)
  const [appVersion, setAppVersion] = useState('')

  const parseJwt = (token: string): { username?: string; is_privileged?: boolean } => {
    try {
      return JSON.parse(atob(token.split('.')[1]))
    } catch {
      return {}
    }
  }

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
    appApi.version()
      .then((r) => setAppVersion(r.data.version))
      .catch(() => setAppVersion(''))
  }, [])

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

  const handleOpenHelp = () => {
    navigate('/help')
  }

  const requirePrivilegedMode = (actionLabel: string): boolean => {
    if (isPrivilegedMode) return true
    window.alert(`${actionLabel} is only available in Sudo mode.`)
    return false
  }

  const enablePrivilegedMode = async () => {
    if (!privilegedPassword.trim()) {
      setPrivilegedError('Password is required.')
      return
    }

    setTogglingPrivileged(true)
    setPrivilegedError('')
    try {
      const response = await authApi.enablePrivilegedMode(privilegedPassword)
      const token = response.data.access_token
      const payload = parseJwt(token)
      setAuth(token, payload.username ?? username ?? '', Boolean(payload.is_privileged))
      setShowPrivilegedPrompt(false)
      setPrivilegedPassword('')
    } catch (err: unknown) {
      setPrivilegedError(getApiErrorMessage(err, 'Could not enable Sudo mode.'))
    } finally {
      setTogglingPrivileged(false)
    }
  }

  const disablePrivilegedMode = async () => {
    setTogglingPrivileged(true)
    setPrivilegedError('')
    try {
      const response = await authApi.disablePrivilegedMode()
      const token = response.data.access_token
      const payload = parseJwt(token)
      setAuth(token, payload.username ?? username ?? '', Boolean(payload.is_privileged))
      setShowPrivilegedPrompt(false)
      setPrivilegedPassword('')
    } catch (err: unknown) {
      setPrivilegedError(getApiErrorMessage(err, 'Could not disable Sudo mode.'))
    } finally {
      setTogglingPrivileged(false)
    }
  }

  const handleDeleteWorkspace = async (workspace: Workspace) => {
    if (!requirePrivilegedMode('Workspace deletion')) return
    if (!window.confirm(`Delete workspace "${workspace.name}" and all its journals/entries?`)) {
      return
    }

    setDeletingWorkspaceId(workspace.id)
    setWorkspaceError('')
    try {
      await workspacesApi.remove(workspace.id)
      const remaining = workspaces.filter((ws) => ws.id !== workspace.id)
      setWorkspaces(remaining)

      if (activeWorkspace?.id === workspace.id) {
        const nextWorkspace = remaining[0] ?? null
        setActiveWorkspace(nextWorkspace)
        setActiveJournal(null)
        setExpandedWs(nextWorkspace?.id ?? null)
        navigate('/')
      } else if (expandedWs === workspace.id) {
        setExpandedWs(activeWorkspace?.id ?? remaining[0]?.id ?? null)
      }
    } catch (err: unknown) {
      setWorkspaceError(getApiErrorMessage(err, 'Could not delete workspace.'))
    } finally {
      setDeletingWorkspaceId(null)
    }
  }

  const handleDeleteJournal = async (journal: Journal) => {
    if (!activeWorkspace) return
    if (!requirePrivilegedMode('Journal deletion')) return
    if (!window.confirm(`Delete journal "${journal.name}" and all entries in it?`)) {
      return
    }

    setDeletingJournalId(journal.id)
    setJournalError('')
    try {
      await journalsApi.remove(activeWorkspace.id, journal.id)
      const remaining = journals.filter((j) => j.id !== journal.id)
      setJournals(remaining)
      if (activeJournal?.id === journal.id) {
        setActiveJournal(null)
        navigate('/')
      }
    } catch (err: unknown) {
      setJournalError(getApiErrorMessage(err, 'Could not delete journal.'))
    } finally {
      setDeletingJournalId(null)
    }
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
    if (!requirePrivilegedMode('Data export')) return

    if (!exportKey.trim() || exportKey.trim().length < 8) {
      setExportError('Encryption key must be at least 8 characters')
      return
    }

    setExportError('')
    setExporting(true)
    try {
      const exportRes = await dataManagementApi.export(exportKey.trim())
      await downloadDumpFile(exportRes.data.filename)
      setShowExportConfirm(false)
      setExportKey('')
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Export failed'
      setExportError(msg)
    } finally {
      setExporting(false)
    }
  }

  const handleTrimMedia = async () => {
    if (!requirePrivilegedMode('Media trim')) return
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
    if (!requirePrivilegedMode('Shred')) return

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
    <aside className={`${styles.sidebar} ${isPrivilegedMode ? styles.sidebarPrivileged : ''}`}>
      <div className={styles.brand}>
        <span>CodexJ</span>
        {appVersion && <span className={styles.brandVersion}>v{appVersion}</span>}
      </div>
      <div className={styles.user}>
        <span>✦ {username}</span>
        {isPrivilegedMode && <span className={styles.privilegedBadge}>Sudo</span>}
      </div>

      <div className={styles.section}>
        <p className={styles.sectionLabel}>Workspaces</p>
        {workspaces.map((ws) => (
          <div key={ws.id}>
            <div className={styles.workspaceRow}>
              <button
                className={`${styles.treeItem} ${activeWorkspace?.id === ws.id ? styles.active : ''}`}
                onClick={() => handleWsClick(ws)}
              >
                {ws.name}
              </button>
              {isPrivilegedMode && (
                <button
                  className={`btn btn-ghost ${styles.deleteMini}`}
                  disabled={deletingWorkspaceId === ws.id}
                  title={`Delete ${ws.name}`}
                  onClick={() => void handleDeleteWorkspace(ws)}
                >
                  {deletingWorkspaceId === ws.id ? '...' : '✖'}
                </button>
              )}
            </div>
            {expandedWs === ws.id && (
              <div className={styles.journals}>
                {journals.map((j) => (
                  <div key={j.id} className={styles.journalRow}>
                    <button
                      className={`${styles.journalItem} ${activeJournal?.id === j.id ? styles.active : ''}`}
                      onClick={() => handleJournalClick(j)}
                    >
                      {j.name}
                    </button>
                    {isPrivilegedMode && (
                      <button
                        className={`btn btn-ghost ${styles.deleteMini}`}
                        disabled={deletingJournalId === j.id}
                        title={`Delete ${j.name}`}
                        onClick={() => void handleDeleteJournal(j)}
                      >
                        {deletingJournalId === j.id ? '...' : '✖'}
                      </button>
                    )}
                  </div>
                ))}
                <div className={`${styles.addRow} ${styles.journalRow} ${showNewJInput ? styles.journalAddRowOpen : ''}`}>
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
                  <button
                    className={`${styles.journalItem} ${styles.journalCreateButton} ${showNewJInput ? styles.journalCreateButtonCompact : ''}`}
                    onClick={handleJournalPlus}
                    aria-label="Create journal"
                  >
                    {showNewJInput ? '✦' : '✦ Create Journal'}
                  </button>
                </div>
                {journalError && <p className="error-text">{journalError}</p>}
              </div>
            )}
          </div>
        ))}
        <div className={`${styles.addRow} ${styles.workspaceRow} ${styles.workspaceCreateRow} ${showNewWsInput ? styles.workspaceAddRowOpen : ''}`}>
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
          <button
            className={`${styles.treeItem} ${styles.workspaceCreateButton} ${showNewWsInput ? styles.workspaceCreateButtonCompact : ''}`}
            onClick={handleWorkspacePlus}
            aria-label="Create workspace"
          >
            {showNewWsInput ? '✦' : '✦ Create Workspace'}
          </button>
        </div>
        {workspaceError && <p className="error-text">{workspaceError}</p>}
      </div>

      <div className={styles.bottom}>
        {!showDeleteConfirm && !showExportConfirm && isPrivilegedMode && (
          <button
            className="btn btn-ghost"
            onClick={() => {
              setShowDeleteConfirm(false)
              setDeleteError('')
              setShowExportConfirm(true)
              setExportError('')
            }}
            disabled={exporting}
            style={{ width: '100%', marginBottom: '0.5rem' }}
          >
            Export
          </button>
        )}

        {!showDeleteConfirm && !showExportConfirm && isPrivilegedMode && (
          <button
            className="btn btn-ghost"
            onClick={() => void handleTrimMedia()}
            disabled={trimmingMedia}
            style={{ width: '100%', marginBottom: '0.5rem' }}
          >
            {trimmingMedia ? 'Trimming...' : 'Trim Media'}
          </button>
        )}

        {!showDeleteConfirm && !showExportConfirm && isPrivilegedMode && (
          <button
            className="btn btn-ghost"
            onClick={() => {
              setShowExportConfirm(false)
              setExportKey('')
              setExportError('')
              setShowDeleteConfirm(true)
            }}
            style={{ width: '100%', marginBottom: '0.5rem' }}
          >
            Shred
          </button>
        )}

        <button
          className={`btn ${isPrivilegedMode ? 'btn-danger' : 'btn-ghost'}`}
          onClick={() => {
            setPrivilegedError('')
            if (isPrivilegedMode) {
              void disablePrivilegedMode()
            } else {
              setShowPrivilegedPrompt((prev) => !prev)
            }
          }}
          disabled={togglingPrivileged}
          style={{ width: '100%', marginBottom: '0.5rem' }}
        >
          {togglingPrivileged
            ? (isPrivilegedMode ? 'Disabling...' : 'Enabling...')
            : 'Sudo Mode'}
        </button>

        {showPrivilegedPrompt && !isPrivilegedMode && (
          <div className={styles.privilegedPrompt}>
            <input
              className="input"
              type="password"
              placeholder="Re-enter password"
              value={privilegedPassword}
              onChange={(e) => {
                setPrivilegedPassword(e.target.value)
                if (privilegedError) setPrivilegedError('')
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  void enablePrivilegedMode()
                }
                if (e.key === 'Escape') {
                  setShowPrivilegedPrompt(false)
                  setPrivilegedPassword('')
                  setPrivilegedError('')
                }
              }}
            />
            {privilegedError && <p className="error-text">{privilegedError}</p>}
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button
                className="btn"
                onClick={() => void enablePrivilegedMode()}
                disabled={togglingPrivileged}
                style={{ flex: 1 }}
              >
                Enable
              </button>
              <button
                className="btn btn-ghost"
                onClick={() => {
                  setShowPrivilegedPrompt(false)
                  setPrivilegedPassword('')
                  setPrivilegedError('')
                }}
                style={{ flex: 1 }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {showExportConfirm ? (
          <div className={styles.deleteConfirm}>
            <p className={styles.deleteWarning}>
              Export your data dump using an encryption key.
            </p>
            <input
              className="input"
              type="password"
              placeholder="Encryption key (min 8 chars)"
              value={exportKey}
              onChange={(e) => {
                setExportKey(e.target.value)
                if (exportError) setExportError('')
              }}
              style={{ marginBottom: '0.5rem' }}
            />
            {exportError && <p className="error-text">{exportError}</p>}
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button
                className="btn"
                onClick={() => void handleExportOnly()}
                disabled={exporting}
                style={{ flex: 1 }}
              >
                {exporting ? 'Exporting...' : 'Export'}
              </button>
              <button
                className="btn btn-ghost"
                onClick={() => {
                  setShowExportConfirm(false)
                  setExportKey('')
                  setExportError('')
                }}
                style={{ flex: 1 }}
              >
                Cancel
              </button>
            </div>
          </div>
        ) : !showDeleteConfirm ? (
          <>
            <div className={styles.bottomRow}>
              <button className="btn btn-ghost" onClick={handleLogout}>
                Log Out
              </button>
              <button className="btn btn-ghost" onClick={handleOpenHelp}>
                Help
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
                style={{ flex: 1 }}
              >
                {exporting ? 'Exporting...' : 'Delete'}
              </button>
              <button
                className="btn btn-ghost"
                onClick={() => {
                  setShowDeleteConfirm(false)
                  setEncryptionKey('')
                  setDeleteError('')
                }}
                style={{ flex: 1 }}
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
