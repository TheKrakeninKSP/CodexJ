import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { journalsApi } from '../services/api'
import { useAuthStore } from '../stores/authStore'
import { useWorkspaceStore } from '../stores/workspaceStore'
import styles from './WorkspaceOverview.module.css'

export default function WorkspaceOverview() {
  const navigate = useNavigate()
  const isPrivilegedMode = useAuthStore((s) => s.isPrivilegedMode)
  const activeWorkspace = useWorkspaceStore((s) => s.activeWorkspace)
  const setActiveJournal = useWorkspaceStore((s) => s.setActiveJournal)
  const journals = useWorkspaceStore((s) => s.journals)
  const [editingDescJournalId, setEditingDescJournalId] = useState<string | null>(null)
  const [editingDesc, setEditingDesc] = useState('')
  const [savingDescId, setSavingDescId] = useState<string | null>(null)

  useEffect(() => {
    // Reset editing state when privilege mode changes to prevent stale edit UI
    if (!isPrivilegedMode) {
      setEditingDescJournalId(null)
      setEditingDesc('')
    }
  }, [isPrivilegedMode])

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
      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div>
            <h2 className={styles.sectionTitle}>{journals.length == 1 ? '1 Journal' : `${journals.length} Journals`}</h2>
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
