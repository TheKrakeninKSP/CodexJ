import { useEffect, useState } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { entriesApi, type Entry } from '../services/api'
import { useWorkspaceStore } from '../stores/workspaceStore'
import styles from './JournalView.module.css'

const TIMEZONE_ALIASES: Record<string, string> = {
  'Asia/Calcutta': 'Asia/Kolkata',
}

function resolveTimeZone(timezone?: string): string | undefined {
  if (!timezone) return undefined
  const normalized = TIMEZONE_ALIASES[timezone] ?? timezone
  try {
    new Intl.DateTimeFormat(undefined, { timeZone: normalized }).format(new Date())
    return normalized
  } catch {
    return undefined
  }
}

function parseApiDate(iso: string): Date {
  const hasOffset = /([zZ]|[+-]\d{2}:?\d{2})$/.test(iso)
  const normalized = hasOffset ? iso : `${iso}Z`
  return new Date(normalized)
}

function fmtDate(iso: string, timezone?: string) {
  const date = parseApiDate(iso)
  const safeTimezone = resolveTimeZone(timezone)
  const options: Intl.DateTimeFormatOptions = {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
  }
  if (safeTimezone) {
    options.timeZone = safeTimezone
  }
  try {
    return date.toLocaleDateString(undefined, options)
  } catch {
    return date.toLocaleDateString(undefined, {
      weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
    })
  }
}

function fmtDateTimeTitle(iso: string, timezone?: string) {
  const date = parseApiDate(iso)
  const safeTimezone = resolveTimeZone(timezone)
  const dateOptions: Intl.DateTimeFormatOptions = {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  }
  const timeOptions: Intl.DateTimeFormatOptions = { hour: 'numeric', hour12: true }
  if (safeTimezone) {
    dateOptions.timeZone = safeTimezone
    timeOptions.timeZone = safeTimezone
  }

  let datePart = ''
  let timePart = ''
  try {
    datePart = date.toLocaleDateString(undefined, dateOptions)
    timePart = date.toLocaleTimeString(undefined, timeOptions).replace(/\s/g, '').toUpperCase()
  } catch {
    datePart = date.toLocaleDateString(undefined, {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    })
    timePart = date.toLocaleTimeString(undefined, { hour: 'numeric', hour12: true }).replace(/\s/g, '').toUpperCase()
  }

  return `${datePart} at ${timePart}`
}

export default function JournalView() {
  const { journalId } = useParams<{ journalId: string }>()
  const navigate = useNavigate()
  const location = useLocation()
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

  useEffect(() => { void load() }, [journalId, location.key])

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
                    <span className={styles.entryDate}>{fmtDate(entry.date_created, entry.timezone)}</span>
                  </>
                ) : (
                  <span className={styles.entryName}>{fmtDateTimeTitle(entry.date_created, entry.timezone)}</span>
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
