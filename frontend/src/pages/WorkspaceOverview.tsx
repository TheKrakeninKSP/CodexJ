import { useNavigate } from 'react-router-dom'
import { useWorkspaceStore } from '../stores/workspaceStore'
import styles from './WorkspaceOverview.module.css'

export default function WorkspaceOverview() {
  const navigate = useNavigate()
  const activeWorkspace = useWorkspaceStore((s) => s.activeWorkspace)
  const setActiveJournal = useWorkspaceStore((s) => s.setActiveJournal)
  const journals = useWorkspaceStore((s) => s.journals)

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
      <div className={styles.grid}>
        {journals.map((j) => (
          <button
            key={j.id}
            className={`paper ${styles.journalCard}`}
            onClick={() => {
              setActiveJournal(j)
              navigate(`/journals/${j.id}`)
            }}
          >
            <span className={styles.jName}>{j.name}</span>
            {j.description && <span className={styles.jDesc}>{j.description}</span>}
          </button>
        ))}
        {journals.length === 0 && (
          <p className={styles.hint}>Add a journal from the sidebar to get started.</p>
        )}
      </div>
    </div>
  )
}
