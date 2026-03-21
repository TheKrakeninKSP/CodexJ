import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { useWorkspaceStore } from '../stores/workspaceStore'
import { workspacesApi, journalsApi, type Workspace, type Journal } from '../services/api'
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
        <button className="btn btn-ghost" onClick={handleLogout}>Log out</button>
      </div>
    </aside>
  )
}
