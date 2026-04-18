import { useEffect, useState } from 'react'
import { entriesApi, journalsApi, type Entry, type Journal, type Workspace, workspacesApi } from '../services/api'
import { useAuthStore } from '../stores/authStore'
import styles from './BinView.module.css'

function notifyBinChanged() {
  window.dispatchEvent(new Event('codexj-bin-changed'))
}

function formatDeletedAt(value?: string | null): string {
  if (!value) return 'Unknown deletion date'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown deletion date'
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function getEntryTitle(entry: Entry): string {
  const trimmedName = entry.name?.trim()
  if (trimmedName) return trimmedName
  return `Untitled ${entry.tags?.[0] ?? 'Entry'}`
}

export default function BinView() {
  const isPrivilegedMode = useAuthStore((state) => state.isPrivilegedMode)
  const [entries, setEntries] = useState<Entry[]>([])
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [journalsByWorkspace, setJournalsByWorkspace] = useState<Record<string, Journal[]>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [restoreEntryId, setRestoreEntryId] = useState<string | null>(null)
  const [restoreWorkspaceId, setRestoreWorkspaceId] = useState('')
  const [restoreJournalId, setRestoreJournalId] = useState('')
  const [loadingJournals, setLoadingJournals] = useState(false)
  const [restoringEntryId, setRestoringEntryId] = useState<string | null>(null)
  const [purgingEntryId, setPurgingEntryId] = useState<string | null>(null)
  const [selectedEntryIds, setSelectedEntryIds] = useState<string[]>([])
  const [bulkPurging, setBulkPurging] = useState(false)

  const getApiErrorMessage = (err: unknown, fallback: string, fieldLabels?: Record<string, string>) => {
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
            const loc = (item as { loc?: unknown[] }).loc
            const rawField = Array.isArray(loc) && loc.length > 1 ? String(loc[loc.length - 1]) : ''
            const field = rawField && fieldLabels?.[rawField] ? fieldLabels[rawField] : rawField
            if (typeof msg === 'string' && field) return `${field}: ${msg}`
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
    let isActive = true
    setLoading(true)
    setError('')

    Promise.all([entriesApi.listDeleted(), workspacesApi.list()])
      .then(([entriesResponse, workspacesResponse]) => {
        if (!isActive) return
        setEntries(entriesResponse.data)
        setSelectedEntryIds([])
        setWorkspaces(workspacesResponse.data)
      })
      .catch((err: unknown) => {
        if (!isActive) return
        setError(getApiErrorMessage(err, 'Could not load Bin entries.'))
      })
      .finally(() => {
        if (!isActive) return
        setLoading(false)
      })

    return () => {
      isActive = false
    }
  }, [])

  const loadJournals = async (workspaceId: string, preferredJournalId?: string | null) => {
    if (!workspaceId) {
      setRestoreJournalId('')
      return
    }

    if (journalsByWorkspace[workspaceId]) {
      const existing = journalsByWorkspace[workspaceId]
      setRestoreJournalId(
        preferredJournalId && existing.some((journal) => journal.id === preferredJournalId)
          ? preferredJournalId
          : existing[0]?.id ?? '',
      )
      return
    }

    setLoadingJournals(true)
    try {
      const response = await journalsApi.list(workspaceId)
      setJournalsByWorkspace((prev) => ({ ...prev, [workspaceId]: response.data }))
      setRestoreJournalId(
        preferredJournalId && response.data.some((journal) => journal.id === preferredJournalId)
          ? preferredJournalId
          : response.data[0]?.id ?? '',
      )
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, 'Could not load journals for restore.'))
      setRestoreJournalId('')
    } finally {
      setLoadingJournals(false)
    }
  }

  const openRestore = async (entry: Entry) => {
    const preferredWorkspaceId =
      entry.deleted_from_workspace_id
      && workspaces.some((workspace) => workspace.id === entry.deleted_from_workspace_id)
        ? entry.deleted_from_workspace_id
        : workspaces[0]?.id ?? ''

    setRestoreEntryId(entry.id)
    setRestoreWorkspaceId(preferredWorkspaceId)
    setRestoreJournalId('')
    setError('')
    await loadJournals(preferredWorkspaceId, entry.deleted_from_journal_id)
  }

  const closeRestore = () => {
    setRestoreEntryId(null)
    setRestoreWorkspaceId('')
    setRestoreJournalId('')
  }

  const performRestore = async (entry: Entry, workspaceId: string, journalId: string) => {
    setRestoringEntryId(entry.id)
    setError('')
    try {
      await entriesApi.restore(entry.id, {
        workspace_id: workspaceId,
        journal_id: journalId,
      })
      setEntries((prev) => prev.filter((item) => item.id !== entry.id))
      setSelectedEntryIds((prev) => prev.filter((id) => id !== entry.id))
      closeRestore()
      notifyBinChanged()
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, 'Could not restore entry.'))
    } finally {
      setRestoringEntryId(null)
    }
  }

  const handleRestore = async (entry: Entry) => {
    if (!restoreWorkspaceId || !restoreJournalId) {
      setError('Choose a workspace and journal before restoring.')
      return
    }

    await performRestore(entry, restoreWorkspaceId, restoreJournalId)
  }

  const handleRestoreToOriginal = async (entry: Entry) => {
    const originalWorkspaceId = entry.deleted_from_workspace_id?.trim() ?? ''
    const originalJournalId = entry.deleted_from_journal_id?.trim() ?? ''

    if (!originalWorkspaceId || !originalJournalId) {
      setError('The original workspace or journal is no longer known for this entry.')
      return
    }

    await performRestore(entry, originalWorkspaceId, originalJournalId)
  }

  const handlePurge = async (entry: Entry) => {
    if (!window.confirm(`Permanently delete "${getEntryTitle(entry)}"?`)) return

    setPurgingEntryId(entry.id)
    setError('')
    try {
      await entriesApi.purge(entry.id)
      setEntries((prev) => prev.filter((item) => item.id !== entry.id))
      setSelectedEntryIds((prev) => prev.filter((id) => id !== entry.id))
      if (restoreEntryId === entry.id) {
        closeRestore()
      }
      notifyBinChanged()
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, 'Could not permanently delete entry.'))
    } finally {
      setPurgingEntryId(null)
    }
  }

  const toggleSelectedEntry = (entryId: string) => {
    setSelectedEntryIds((prev) =>
      prev.includes(entryId) ? prev.filter((id) => id !== entryId) : [...prev, entryId],
    )
  }

  const toggleSelectAll = () => {
    if (selectedEntryIds.length === entries.length) {
      setSelectedEntryIds([])
      return
    }
    setSelectedEntryIds(entries.map((entry) => entry.id))
  }

  const handleBulkPurge = async () => {
    if (selectedEntryIds.length === 0) return
    if (!window.confirm(`Permanently delete ${selectedEntryIds.length} selected entr${selectedEntryIds.length === 1 ? 'y' : 'ies'}?`)) {
      return
    }

    setBulkPurging(true)
    setError('')
    try {
      for (const entryId of selectedEntryIds) {
        await entriesApi.purge(entryId)
      }
      setEntries((prev) => prev.filter((entry) => !selectedEntryIds.includes(entry.id)))
      if (restoreEntryId && selectedEntryIds.includes(restoreEntryId)) {
        closeRestore()
      }
      setSelectedEntryIds([])
      notifyBinChanged()
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, 'Could not permanently delete selected entries.'))
    } finally {
      setBulkPurging(false)
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.heading}>Bin</h1>
          <p className={styles.sub}>Deleted entries can be restored into any journal you still own.</p>
        </div>
        {isPrivilegedMode && entries.length > 0 && (
          <div className={styles.toolbar}>
            <label className={styles.bulkSelectLabel}>
              <input
                type="checkbox"
                checked={entries.length > 0 && selectedEntryIds.length === entries.length}
                onChange={toggleSelectAll}
              />
              <span>Select all</span>
            </label>
            <button
              className="btn btn-danger"
              disabled={selectedEntryIds.length === 0 || bulkPurging}
              onClick={() => void handleBulkPurge()}
            >
              {bulkPurging ? 'Deleting…' : `Purge Selected (${selectedEntryIds.length})`}
            </button>
          </div>
        )}
      </div>

      {error && <p className={styles.error}>{error}</p>}

      {loading ? (
        <p className={styles.hint}>Loading Bin…</p>
      ) : entries.length === 0 ? (
        <p className={styles.hint}>No deleted entries.</p>
      ) : (
        <div className={styles.list}>
          {entries.map((entry) => {
            const showRestorePanel = restoreEntryId === entry.id
            const availableJournals = restoreWorkspaceId ? journalsByWorkspace[restoreWorkspaceId] ?? [] : []

            return (
              <article key={entry.id} className={`paper ${styles.card}`}>
                <div className={styles.cardTop}>
                  {isPrivilegedMode && (
                    <label className={styles.cardSelect}>
                      <input
                        type="checkbox"
                        checked={selectedEntryIds.includes(entry.id)}
                        onChange={() => toggleSelectedEntry(entry.id)}
                      />
                    </label>
                  )}
                  <div className={styles.cardInfo}>
                    <h2 className={styles.cardTitle}>{getEntryTitle(entry)}</h2>
                    <p className={styles.cardMeta}>
                      {entry.tags?.join(', ')} · Deleted {formatDeletedAt(entry.deleted_at)}
                    </p>
                    <p className={styles.cardContext}>
                      From {entry.deleted_from_workspace_name || 'Deleted workspace'} / {entry.deleted_from_journal_name || 'Deleted journal'}
                    </p>
                  </div>

                  <div className={styles.cardActions}>
                    {isPrivilegedMode ? (
                      <>
                        <button
                          className="btn btn-ghost"
                          disabled={restoringEntryId === entry.id}
                          onClick={() => void handleRestoreToOriginal(entry)}
                        >
                          {restoringEntryId === entry.id ? 'Restoring…' : 'Restore to Original'}
                        </button>
                        <button className="btn btn-ghost" onClick={() => void openRestore(entry)}>
                          Restore
                        </button>
                        <button
                          className="btn btn-danger"
                          disabled={purgingEntryId === entry.id}
                          onClick={() => void handlePurge(entry)}
                        >
                          {purgingEntryId === entry.id ? 'Deleting…' : 'Delete Permanently'}
                        </button>
                      </>
                    ) : (
                      <span className={styles.permissionHint}>Restore and purge require Sudo mode.</span>
                    )}
                  </div>
                </div>

                {showRestorePanel && isPrivilegedMode && (
                  <div className={styles.restorePanel}>
                    <div className={styles.restoreHeader}>
                      <p className={styles.restoreEyebrow}>Restore Target</p>
                      <p className={styles.restoreHint}>Choose a workspace first, then a journal inside it.</p>
                    </div>

                    <div className={styles.restoreGrid}>
                      <label className={styles.restoreField}>
                        <span className={styles.restoreLabel}>Workspace</span>
                        <select
                          className="input"
                          value={restoreWorkspaceId}
                          onChange={(event) => {
                            const nextWorkspaceId = event.target.value
                            setRestoreWorkspaceId(nextWorkspaceId)
                            void loadJournals(nextWorkspaceId)
                          }}
                        >
                          <option value="">Select workspace</option>
                          {workspaces.map((workspace) => (
                            <option key={workspace.id} value={workspace.id}>{workspace.name}</option>
                          ))}
                        </select>
                      </label>

                      <label className={styles.restoreField}>
                        <span className={styles.restoreLabel}>Journal</span>
                        <select
                          className="input"
                          value={restoreJournalId}
                          disabled={!restoreWorkspaceId || loadingJournals}
                          onChange={(event) => setRestoreJournalId(event.target.value)}
                        >
                          <option value="">Select journal</option>
                          {availableJournals.map((journal) => (
                            <option key={journal.id} value={journal.id}>{journal.name}</option>
                          ))}
                        </select>
                      </label>
                    </div>

                    <div className={styles.restoreActions}>
                      <button
                        className="btn"
                        disabled={!restoreWorkspaceId || !restoreJournalId || restoringEntryId === entry.id || loadingJournals}
                        onClick={() => void handleRestore(entry)}
                      >
                        {restoringEntryId === entry.id ? 'Restoring…' : 'Restore Entry'}
                      </button>
                      <button className="btn btn-ghost" onClick={closeRestore}>Cancel</button>
                    </div>
                  </div>
                )}
              </article>
            )
          })}
        </div>
      )}
    </div>
  )
}