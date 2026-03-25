import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { entriesApi, type Entry } from '../services/api'
import { useWorkspaceStore } from '../stores/workspaceStore'
import styles from './JournalView.module.css'

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
  })
}

function fmtDateTimeTitle(iso: string) {
  const date = new Date(iso)
  const datePart = date.toLocaleDateString(undefined, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
  const timePart = date
    .toLocaleTimeString(undefined, { hour: 'numeric', hour12: true })
    .replace(/\s/g, '')
    .toUpperCase()

  return `${datePart} at ${timePart}`
}

export default function JournalView() {
  const { journalId } = useParams<{ journalId: string }>()
  const navigate = useNavigate()
  const activeJournal = useWorkspaceStore((s) => s.activeJournal)
  const journals = useWorkspaceStore((s) => s.journals)
  const [entries, setEntries] = useState<Entry[]>([])
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [loading, setLoading] = useState(true)

  const matchingActiveJournal =
    activeJournal && activeJournal.id === journalId ? activeJournal : null
  const currentJournalName =
    matchingActiveJournal?.name ?? journals.find((j) => j.id === journalId)?.name

  const load = async () => {
    if (!journalId) return
    setLoading(true)
    try {
      if (search.trim()) {
        const r = await entriesApi.search({
          q: search,
          journal_id: journalId,
          entry_type: typeFilter || undefined,
        })
        setEntries(r.data)
      } else {
        const r = await entriesApi.list(journalId)
        setEntries(typeFilter ? r.data.filter((e) => e.type === typeFilter) : r.data)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [journalId])

  const uniqueTypes = [...new Set(entries.map((e) => e.type))]

  return (
    <div className={styles.page}>
      <h1 className={styles.journalTitle}>{currentJournalName ?? 'Journal'}</h1>
      <p className={styles.journalMeta}>
        {entries.length} entr{entries.length === 1 ? 'y' : 'ies'}
      </p>
      <div className={styles.toolbar}>
        <input
          className="input"
          placeholder="Search entries…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && load()}
          style={{ maxWidth: 320 }}
        />
        {uniqueTypes.length > 0 && (
          <select
            className="input"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            style={{ maxWidth: 180 }}
          >
            <option value="">All types</option>
            {uniqueTypes.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        )}
        <button className="btn" onClick={load}>Search</button>
        <button
          className="btn"
          style={{ marginLeft: 'auto' }}
          onClick={() => navigate(`/entries/new?journal=${journalId}`)}
        >
          + New Entry
        </button>
      </div>

      {loading ? (
        <p className={styles.hint}>Loading…</p>
      ) : entries.length === 0 ? (
        <p className={styles.hint}>No entries yet. Create one!</p>
      ) : (
        <div className={styles.list}>
          {entries.map((entry) => (
            <button
              key={entry.id}
              className={`paper ${styles.entryRow}`}
              onClick={() => {
                console.log('Entry clicked, navigating to:', `/entries/${entry.id}`)
                navigate(`/entries/${entry.id}`)
              }}
            >
              <span className={styles.entryMain}>
                {entry.name?.trim() ? (
                  <>
                    <span className={styles.entryName}>{entry.name}</span>
                    <span className={styles.entryDate}>{fmtDate(entry.date_created)}</span>
                  </>
                ) : (
                  <span className={styles.entryName}>{fmtDateTimeTitle(entry.date_created)}</span>
                )}
              </span>
              <span className={styles.entryType}>{entry.type}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
