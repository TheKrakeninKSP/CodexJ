import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { entryTypesApi, journalsApi, type EntryType } from '../services/api'
import { useWorkspaceStore } from '../stores/workspaceStore'
import styles from './WorkspaceOverview.module.css'

export default function WorkspaceOverview() {
  const navigate = useNavigate()
  const isPrivilegedMode = useAuthStore((s) => s.isPrivilegedMode)
  const activeWorkspace = useWorkspaceStore((s) => s.activeWorkspace)
  const setActiveJournal = useWorkspaceStore((s) => s.setActiveJournal)
  const journals = useWorkspaceStore((s) => s.journals)
  const [entryTypes, setEntryTypes] = useState<EntryType[]>([])
  const [loadingTypes, setLoadingTypes] = useState(false)
  const [typeError, setTypeError] = useState('')
  const [deletingTypeId, setDeletingTypeId] = useState<string | null>(null)
  const [editingDescJournalId, setEditingDescJournalId] = useState<string | null>(null)
  const [editingDesc, setEditingDesc] = useState('')
  const [savingDescId, setSavingDescId] = useState<string | null>(null)

  const getApiErrorMessage = (err: unknown, fallback: string) => {
    const detail = (err as { response?: { data?: { detail?: unknown; message?: unknown } } })
      ?.response?.data?.detail
    const message = (err as { response?: { data?: { detail?: unknown; message?: unknown } } })
      ?.response?.data?.message

    if (typeof detail === 'string' && detail.trim()) return detail
    if (typeof message === 'string' && message.trim()) return message
    return fallback
  }

  useEffect(() => {
    if (!activeWorkspace) {
      setEntryTypes([])
      setTypeError('')
      return
    }

    let isActive = true
    setLoadingTypes(true)
    setTypeError('')

    entryTypesApi.list(activeWorkspace.id)
      .then((response) => {
        if (!isActive) return
        setEntryTypes(response.data)
      })
      .catch((err: unknown) => {
        if (!isActive) return
        setTypeError(getApiErrorMessage(err, 'Could not load entry types.'))
        setEntryTypes([])
      })
      .finally(() => {
        if (!isActive) return
        setLoadingTypes(false)
      })

    return () => {
      isActive = false
    }
  }, [activeWorkspace])

  const handleDeleteEntryType = async (entryType: EntryType) => {
    if (!activeWorkspace || deletingTypeId) return
    if (!window.confirm(`Delete entry type "${entryType.name}"?`)) return

    setDeletingTypeId(entryType.id)
    setTypeError('')
    try {
      await entryTypesApi.remove(activeWorkspace.id, entryType.id)
      setEntryTypes((prev) => prev.filter((current) => current.id !== entryType.id))
    } catch (err: unknown) {
      setTypeError(getApiErrorMessage(err, 'Could not delete entry type.'))
    } finally {
      setDeletingTypeId(null)
    }
  }

  const handleSaveDescription = async (journalId: string) => {
    if (!activeWorkspace) return
    setSavingDescId(journalId)
    try {
      await journalsApi.update(activeWorkspace.id, journalId, { description: editingDesc })
      // Update local store journals list
      const setJournals = useWorkspaceStore.getState().setJournals
      const currentJournals = useWorkspaceStore.getState().journals
      setJournals(currentJournals.map((j) => j.id === journalId ? { ...j, description: editingDesc } : j))
    } catch {
      // fail silently — description is non-critical
    } finally {
      setSavingDescId(null)
      setEditingDescJournalId(null)
    }
  }

  if (!activeWorkspace) {
    return (
      <div className={styles.empty}>
        <p>Select or create a workspace from the sidebar.</p>
      </div>
    )
  }

  return (
    <div className={styles.page}>
      <h1 className={styles.heading}>{activeWorkspace.name}</h1>
      <p className={styles.sub}>
        {journals.length} journal{journals.length !== 1 ? 's' : ''}
      </p>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div>
            <h2 className={styles.sectionTitle}>Entry Types</h2>
            <p className={styles.sectionHint}>
              Workspace-scoped types used by entries in this workspace.
            </p>
          </div>
        </div>

        {typeError && <p className={styles.error}>{typeError}</p>}

        {loadingTypes ? (
          <p className={styles.hint}>Loading entry types…</p>
        ) : entryTypes.length === 0 ? (
          <p className={styles.hint}>No entry types yet. They appear here after entries are saved.</p>
        ) : (
          <div className={styles.typeList}>
            {entryTypes.map((entryType) => (
              <div key={entryType.id} className={`paper ${styles.typeCard}`}>
                <div className={styles.typeInfo}>
                  <span className={styles.typeName}>{entryType.name}</span>
                  <span className={styles.typeCount}>
                    {entryType.entry_count} {entryType.entry_count === 1 ? 'entry' : 'entries'}
                  </span>
                </div>
                <div className={styles.typeActions}>
                  {isPrivilegedMode && (
                    <button
                      className="btn btn-ghost"
                      onClick={() => void handleDeleteEntryType(entryType)}
                      disabled={deletingTypeId === entryType.id}
                    >
                      {deletingTypeId === entryType.id ? 'Deleting…' : 'Delete'}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div>
            <h2 className={styles.sectionTitle}>Journals</h2>
          </div>
        </div>
      <div className={styles.grid}>
        {journals.map((j) => (
          <div key={j.id} className={`paper ${styles.journalCard}`}>
            <button
              className={styles.journalCardMain}
              onClick={() => {
                setActiveJournal(j)
                navigate(`/journals/${j.id}`)
              }}
            >
              <span className={styles.jName}>{j.name}</span>
              {j.description && editingDescJournalId !== j.id && (
                <span className={styles.jDesc}>{j.description}</span>
              )}
            </button>
            {isPrivilegedMode && editingDescJournalId === j.id ? (
              <div className={styles.descEditRow}>
                <input
                  className={`input ${styles.descInput}`}
                  placeholder="Journal description (optional)"
                  value={editingDesc}
                  onChange={(e) => setEditingDesc(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void handleSaveDescription(j.id)
                    if (e.key === 'Escape') setEditingDescJournalId(null)
                  }}
                  autoFocus
                />
                <button
                  className="btn btn-ghost"
                  style={{ fontSize: '0.8rem', padding: '0.25rem 0.6rem' }}
                  disabled={savingDescId === j.id}
                  onClick={() => void handleSaveDescription(j.id)}
                >
                  {savingDescId === j.id ? '…' : 'Save'}
                </button>
                <button
                  className="btn btn-ghost"
                  style={{ fontSize: '0.8rem', padding: '0.25rem 0.6rem' }}
                  onClick={() => setEditingDescJournalId(null)}
                >
                  Cancel
                </button>
              </div>
            ) : isPrivilegedMode ? (
              <button
                className={`btn btn-ghost ${styles.editDescBtn}`}
                onClick={(e) => {
                  e.stopPropagation()
                  setEditingDescJournalId(j.id)
                  setEditingDesc(j.description ?? '')
                }}
              >
                {j.description ? 'Edit description' : '+ Description'}
              </button>
            ) : null}
          </div>
        ))}
        {journals.length === 0 && (
          <p className={styles.hint}>Add a journal from the sidebar to get started.</p>
        )}
      </div>
      </section>
    </div>
  )
}
