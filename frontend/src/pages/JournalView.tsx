import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { entriesApi, type Entry } from '../services/api'
import styles from './JournalView.module.css'

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
  })
}

export default function JournalView() {
  const { journalId } = useParams<{ journalId: string }>()
  const navigate = useNavigate()
  const [entries, setEntries] = useState<Entry[]>([])
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [loading, setLoading] = useState(true)

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
              <span className={styles.entryDate}>{fmtDate(entry.date_created)}</span>
              <span className={styles.entryType}>{entry.type}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
