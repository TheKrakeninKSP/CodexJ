import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
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
import { themeOptions, type ThemeName } from '../theme'
import { useThemeStore } from '../stores/themeStore'
import styles from './Sidebar.module.css'

export default function Sidebar() {
  const location = useLocation()
  const navigate = useNavigate()
  const logout = useAuthStore((s) => s.logout)
  const setAuth = useAuthStore((s) => s.setAuth)
  const username = useAuthStore((s) => s.username)
  const isPrivilegedMode = useAuthStore((s) => s.isPrivilegedMode)
  const theme = useThemeStore((s) => s.theme)
  const setTheme = useThemeStore((s) => s.setTheme)
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
  const [themeError, setThemeError] = useState('')
  const [savingTheme, setSavingTheme] = useState(false)
  const [showAppearanceSection, setShowAppearanceSection] = useState(false)

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

  const handleOpenBin = () => {
    setActiveJournal(null)
    navigate('/bin')
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
      window.alert(
        `Trim complete. Removed ${res.data.deleted_count} of ${res.data.scanned_count} resources, including ${res.data.deleted_media_count} media items and ${res.data.deleted_entry_type_count} entry types.`,
      )
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

  const handleThemeChange = async (nextTheme: ThemeName) => {
    if (nextTheme === theme || savingTheme) return

    const previousTheme = theme
    setTheme(nextTheme)
    setThemeError('')
    setSavingTheme(true)
    try {
      await authApi.updatePreferences({ theme: nextTheme })
    } catch (err: unknown) {
      setTheme(previousTheme)
      setThemeError(getApiErrorMessage(err, 'Could not update theme.'))
    } finally {
      setSavingTheme(false)
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
        <div className={styles.sidebarUtilityRow}>
          <button
            type="button"
            className={`${styles.treeItem} ${styles.sidebarUtilityButton} ${location.pathname === '/bin' ? styles.active : ''}`}
            onClick={handleOpenBin}
          >
            Bin
          </button>
        </div>
      </div>

      <div className={styles.bottom}>
        <div className={styles.commandSection}>
          <button
            type="button"
            className={`${styles.commandRow} ${styles.commandSectionToggle}`}
            onClick={() => setShowAppearanceSection((prev) => !prev)}
            aria-expanded={showAppearanceSection}
          >
            <span className={styles.commandIcon} aria-hidden="true">
              {showAppearanceSection ? '▾' : '▸'}
            </span>
            <span className={styles.commandText}>Theme</span>
            <span className={styles.commandMeta}>{themeOptions.find((option) => option.value === theme)?.label}</span>
          </button>
          {showAppearanceSection && (
            <div className={styles.commandList} role="list">
              {themeOptions.map((option) => {
                const active = option.value === theme
                return (
                  <button
                    key={option.value}
                    type="button"
                    className={`${styles.commandRow} ${styles.commandSubRow} ${active ? styles.commandRowActive : ''}`}
                    onClick={() => void handleThemeChange(option.value as ThemeName)}
                    disabled={savingTheme}
                    aria-pressed={active}
                  >
                    <span className={styles.commandIcon} aria-hidden="true">
                      {active ? '●' : '○'}
                    </span>
                    <span className={styles.commandText}>{option.label}</span>
                    {active && <span className={styles.commandMeta}>Current</span>}
                  </button>
                )
              })}
            </div>
          )}
          {themeError && <p className="error-text">{themeError}</p>}
        </div>

        <div className={styles.commandSection}>
          <p className={styles.commandSectionLabel}>Actions</p>
          <div className={styles.commandList}>
            <button
              type="button"
              className={`${styles.commandRow} ${isPrivilegedMode ? styles.commandRowDanger : ''}`}
              onClick={() => {
                setPrivilegedError('')
                if (isPrivilegedMode) {
                  void disablePrivilegedMode()
                } else {
                  setShowPrivilegedPrompt((prev) => !prev)
                }
              }}
              disabled={togglingPrivileged}
            >
              <span className={styles.commandIcon} aria-hidden="true">■</span>
              <span className={styles.commandText}>Sudo Mode</span>
              <span className={styles.commandMeta}>
                {togglingPrivileged
                  ? (isPrivilegedMode ? 'Disabling...' : 'Enabling...')
                  : (isPrivilegedMode ? 'On' : 'Off')}
              </span>
            </button>

            {!showDeleteConfirm && !showExportConfirm && isPrivilegedMode && (
              <>
                <button
                  type="button"
                  className={styles.commandRow}
                  onClick={() => {
                    setShowDeleteConfirm(false)
                    setDeleteError('')
                    setShowExportConfirm(true)
                    setExportError('')
                  }}
                  disabled={exporting}
                >
                  <span className={styles.commandIcon} aria-hidden="true">⇩</span>
                  <span className={styles.commandText}>Export Data</span>
                </button>

                <button
                  type="button"
                  className={styles.commandRow}
                  onClick={() => void handleTrimMedia()}
                  disabled={trimmingMedia}
                >
                  <span className={styles.commandIcon} aria-hidden="true">◌</span>
                  <span className={styles.commandText}>Trim Media</span>
                  {trimmingMedia && <span className={styles.commandMeta}>Running</span>}
                </button>

                <button
                  type="button"
                  className={`${styles.commandRow} ${styles.commandRowDanger}`}
                  onClick={() => {
                    setShowExportConfirm(false)
                    setExportKey('')
                    setExportError('')
                    setShowDeleteConfirm(true)
                  }}
                >
                  <span className={styles.commandIcon} aria-hidden="true">×</span>
                  <span className={styles.commandText}>Shred Account</span>
                </button>
              </>
            )}

            <button
              type="button"
              className={styles.commandRow}
              onClick={handleOpenHelp}
            >
              <span className={styles.commandIcon} aria-hidden="true">?</span>
              <span className={styles.commandText}>Help</span>
            </button>

            <button
              type="button"
              className={styles.commandRow}
              onClick={handleLogout}
            >
              <span className={styles.commandIcon} aria-hidden="true">↩</span>
              <span className={styles.commandText}>Log Out</span>
            </button>
          </div>
        </div>

        {showPrivilegedPrompt && !isPrivilegedMode && (
          <div className={styles.inlinePanel}>
            <div className={styles.inlinePanelHeader}>
              <p className={styles.inlinePanelEyebrow}>Security</p>
              <p className={styles.inlinePanelTitle}>Enable Sudo Mode</p>
              <p className={styles.inlinePanelHint}>Re-enter your password to unlock privileged actions.</p>
            </div>
            <label className={styles.inlinePanelLabel} htmlFor="sudo-password-input">Password</label>
            <input
              id="sudo-password-input"
              className={`input ${styles.inlinePanelInput}`}
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
            <div className={styles.inlinePanelActions}>
              <button
                className={`${styles.inlinePanelActionButton} ${styles.inlinePanelActionButtonPrimary}`}
                onClick={() => void enablePrivilegedMode()}
                disabled={togglingPrivileged}
              >
                Enable
              </button>
              <button
                className={`${styles.inlinePanelActionButton} ${styles.inlinePanelActionButtonSecondary}`}
                onClick={() => {
                  setShowPrivilegedPrompt(false)
                  setPrivilegedPassword('')
                  setPrivilegedError('')
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {showExportConfirm ? (
          <div className={styles.inlinePanel}>
            <div className={styles.inlinePanelHeader}>
              <p className={styles.inlinePanelEyebrow}>Export</p>
              <p className={styles.inlinePanelTitle}>Create Encrypted Dump</p>
              <p className={styles.inlinePanelHint}>Provide the encryption key you want to use for this export.</p>
            </div>
            <label className={styles.inlinePanelLabel} htmlFor="export-key-input">Encryption Key</label>
            <input
              id="export-key-input"
              className={`input ${styles.inlinePanelInput}`}
              type="password"
              placeholder="Encryption key (min 8 chars)"
              value={exportKey}
              onChange={(e) => {
                setExportKey(e.target.value)
                if (exportError) setExportError('')
              }}
            />
            {exportError && <p className="error-text">{exportError}</p>}
            <div className={styles.inlinePanelActions}>
              <button
                className={`${styles.inlinePanelActionButton} ${styles.inlinePanelActionButtonPrimary}`}
                onClick={() => void handleExportOnly()}
                disabled={exporting}
              >
                {exporting ? 'Exporting...' : 'Export'}
              </button>
              <button
                className={`${styles.inlinePanelActionButton} ${styles.inlinePanelActionButtonSecondary}`}
                onClick={() => {
                  setShowExportConfirm(false)
                  setExportKey('')
                  setExportError('')
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        ) : showDeleteConfirm ? (
          <div className={styles.inlinePanel}>
            <div className={styles.inlinePanelHeader}>
              <p className={`${styles.inlinePanelEyebrow} ${styles.inlinePanelEyebrowDanger}`}>Danger Zone</p>
              <p className={`${styles.inlinePanelTitle} ${styles.inlinePanelTitleDanger}`}>
                Export and Delete Account
              </p>
              <p className={styles.inlinePanelHint}>Your account will be exported and then permanently removed.</p>
            </div>
            <label className={styles.inlinePanelLabel} htmlFor="shred-key-input">Encryption Key</label>
            <input
              id="shred-key-input"
              className={`input ${styles.inlinePanelInput}`}
              type="password"
              placeholder="Encryption key (min 8 chars)"
              value={encryptionKey}
              onChange={(e) => setEncryptionKey(e.target.value)}
            />
            {deleteError && <p className="error-text">{deleteError}</p>}
            <div className={styles.inlinePanelActions}>
              <button
                className={`${styles.inlinePanelActionButton} ${styles.inlinePanelActionButtonDanger}`}
                onClick={handleExportAndDelete}
                disabled={exporting}
              >
                {exporting ? 'Exporting...' : 'Delete'}
              </button>
              <button
                className={`${styles.inlinePanelActionButton} ${styles.inlinePanelActionButtonSecondary}`}
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
        ) : null}
      </div>
    </aside>
  )
}
