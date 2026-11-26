import { useCallback, useEffect, useMemo, useState } from 'react'
import { entriesApi, journalsApi, type BinEntry, type Journal, type Workspace, workspacesApi } from '../services/api'
import { useAuthStore } from '../stores/authStore'
import { getApiErrorMessage } from '../utils/errors'
import styles from './BinView.module.css'

function notifyBinChanged() {
  window.dispatchEvent(new Event('codexj-bin-changed'))
}

/** Tells the sidebar a journal (and maybe its workspace) came back. */
function notifyContainersChanged() {
  window.dispatchEvent(new Event('codexj-containers-changed'))
}

type DeletedJournal = {
  journalId: string
  journalName: string
  workspaceId: string
  workspaceName: string
  /** Entries "Restore journal" brings back (binned along with the journal). */
  withJournalCount: number
  totalCount: number
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

function getEntryTitle(entry: BinEntry): string {
  const trimmedName = entry.name?.trim()
  if (trimmedName) return trimmedName
  return `Untitled ${entry.tags?.[0] ?? 'Entry'}`
}

export default function BinView() {
  const isPrivilegedMode = useAuthStore((s) => s.isPrivilegedMode)
  const [entries, setEntries] = useState<BinEntry[]>([])
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
  const [restoringJournalId, setRestoringJournalId] = useState<string | null>(null)
  const [notice, setNotice] = useState('')

  const loadBin = useCallback(async (isActive: () => boolean = () => true) => {
    setError('')
    try {
      const [entriesResponse, workspacesResponse] = await Promise.all([
        entriesApi.listDeleted(),
        workspacesApi.list(),
      ])
      if (!isActive()) return
      setEntries(entriesResponse.data)
      setSelectedEntryIds([])
      setWorkspaces(workspacesResponse.data)
      setJournalsByWorkspace({})
    } catch (err: unknown) {
      if (!isActive()) return
      setError(getApiErrorMessage(err, 'Could not load Bin entries.'))
    }
  }, [])

  useEffect(() => {
    let active = true
    setLoading(true)
    void loadBin(() => active).finally(() => {
      if (active) setLoading(false)
    })
    return () => {
      active = false
    }
  }, [loadBin])

  // Binned journals that still hold entries, each restorable as a whole.
  const deletedJournals = useMemo<DeletedJournal[]>(() => {
    const byId = new Map<string, DeletedJournal>()
    for (const entry of entries) {
      if (!entry.original_journal_deleted) continue
      const group = byId.get(entry.journal_id) ?? {
        journalId: entry.journal_id,
        journalName: entry.original_journal_name || 'Deleted journal',
        workspaceId: entry.original_workspace_id ?? '',
        workspaceName: entry.original_workspace_name || 'Deleted workspace',
        withJournalCount: 0,
        totalCount: 0,
      }
      group.totalCount += 1
      if (entry.binned_with_container) group.withJournalCount += 1
      byId.set(entry.journal_id, group)
    }
    return [...byId.values()].sort((a, b) => a.journalName.localeCompare(b.journalName))
  }, [entries])

  const handleRestoreJournal = async (group: DeletedJournal) => {
    setRestoringJournalId(group.journalId)
    setError('')
    setNotice('')
    try {
      const { data } = await journalsApi.restore(group.workspaceId, group.journalId)
      const restored = `${data.entries_restored} entr${data.entries_restored === 1 ? 'y' : 'ies'}`
      setNotice(
        `Restored journal "${data.journal.name}" with ${restored}`
          + (data.workspace_restored ? ` and its workspace "${data.journal.workspace_name}".` : '.'),
      )
      closeRestore()
      await loadBin()
      notifyBinChanged()
      notifyContainersChanged()
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, 'Could not restore journal.'))
    } finally {
      setRestoringJournalId(null)
    }
  }

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

  const openRestore = async (entry: BinEntry) => {
    // The journal's *current* workspace, so a journal moved since still preselects.
    const preferredWorkspaceId =
      entry.original_workspace_id
        && workspaces.some((workspace) => workspace.id === entry.original_workspace_id)
        ? entry.original_workspace_id
        : workspaces[0]?.id ?? ''

    setRestoreEntryId(entry.id)
    setRestoreWorkspaceId(preferredWorkspaceId)
    setRestoreJournalId('')
    setError('')
    await loadJournals(preferredWorkspaceId, entry.original_journal_deleted ? null : entry.journal_id)
  }

  const closeRestore = () => {
    setRestoreEntryId(null)
    setRestoreWorkspaceId('')
    setRestoreJournalId('')
  }

  const performRestore = async (entry: BinEntry, workspaceId: string, journalId: string) => {
    setRestoringEntryId(entry.id)
    setError('')
    try {
      await entriesApi.restore(entry.id, {
        workspace_id: workspaceId,
        journal_id: journalId,
      })
      setEntries((prev) => prev.filter((item) => item.id !== entry.id))
      setSelectedEntryIds((prev) => prev.filter((id) => id !== entry.id))
      setNotice('')
      closeRestore()
      notifyBinChanged()
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, 'Could not restore entry.'))
    } finally {
      setRestoringEntryId(null)
    }
  }

  const handleRestore = async (entry: BinEntry) => {
    if (!restoreWorkspaceId || !restoreJournalId) {
      setError('Choose a workspace and journal before restoring.')
      return
    }

    await performRestore(entry, restoreWorkspaceId, restoreJournalId)
  }

  const handleRestoreToOriginal = async (entry: BinEntry) => {
    if (entry.original_journal_deleted || !entry.original_workspace_id) {
      setError('The original journal is in the Bin. Restore the journal, or pick another one.')
      return
    }
    await performRestore(entry, entry.original_workspace_id, entry.journal_id)
  }

  const handlePurge = async (entry: BinEntry) => {
    if (!window.confirm(`Permanently delete "${getEntryTitle(entry)}"?`)) return

    setPurgingEntryId(entry.id)
    setError('')
    try {
      await entriesApi.purge(entry.id)
      setEntries((prev) => prev.filter((item) => item.id !== entry.id))
      setSelectedEntryIds((prev) => prev.filter((id) => id !== entry.id))
      setNotice('')
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
          <p className={styles.sub}>Deleted entries can be restored into any journal you still own. Deleted journals can be restored whole.</p>
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
      {notice && <p className={styles.notice}>{notice}</p>}

      {!loading && deletedJournals.length > 0 && (
        <section className={styles.section} aria-labelledby="deleted-journals-heading">
          <h2 id="deleted-journals-heading" className={styles.sectionHeading}>Deleted journals</h2>
          <div className={styles.list}>
            {deletedJournals.map((group) => (
              <article key={group.journalId} className={`paper ${styles.card}`}>
                <div className={styles.cardTop}>
                  <div className={styles.cardInfo}>
                    <h3 className={styles.cardTitle}>{group.journalName}</h3>
                    <p className={styles.cardMeta}>
                      {group.totalCount} entr{group.totalCount === 1 ? 'y' : 'ies'} in the Bin
                      {group.withJournalCount < group.totalCount
                        && ` · ${group.withJournalCount} come back with the journal`}
                    </p>
                    <p className={styles.cardContext}>From {group.workspaceName}</p>
                  </div>
                  <div className={styles.cardActions}>
                    <button
                      className="btn"
                      disabled={restoringJournalId === group.journalId || !group.workspaceId}
                      onClick={() => void handleRestoreJournal(group)}
                    >
                      {restoringJournalId === group.journalId ? 'Restoring…' : 'Restore Journal'}
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
          <h2 className={styles.sectionHeading}>Entries</h2>
        </section>
      )}

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
                      From {entry.original_workspace_name || 'Deleted workspace'} / {entry.original_journal_name || 'Deleted journal'}
                      {entry.original_journal_deleted && ' (journal deleted)'}
                    </p>
                  </div>

                  <div className={styles.cardActions}>
                    <button
                      className="btn btn-ghost"
                      disabled={restoringEntryId === entry.id || entry.original_journal_deleted}
                      title={entry.original_journal_deleted
                        ? 'The original journal is in the Bin - restore the journal above, or pick another one'
                        : undefined}
                      onClick={() => void handleRestoreToOriginal(entry)}
                    >
                      {restoringEntryId === entry.id ? 'Restoring…' : 'Restore to Original'}
                    </button>
                    <button className="btn btn-ghost" onClick={() => void openRestore(entry)}>
                      Restore
                    </button>
                    {isPrivilegedMode ? (
                      <button
                        className="btn btn-danger"
                        disabled={purgingEntryId === entry.id}
                        onClick={() => void handlePurge(entry)}
                      >
                        {purgingEntryId === entry.id ? 'Deleting…' : 'Delete Permanently'}
                      </button>
                    ) : (
                      <span className={styles.permissionHint}>Permanent deletion requires Sudo mode.</span>
                    )}
                  </div>
                </div>

                {showRestorePanel && (
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