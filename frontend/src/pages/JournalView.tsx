import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { dataManagementApi, entriesApi, type Entry } from '../services/api'
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
  const activeWorkspace = useWorkspaceStore((s) => s.activeWorkspace)
  const activeJournal = useWorkspaceStore((s) => s.activeJournal)
  const journals = useWorkspaceStore((s) => s.journals)
  const [entries, setEntries] = useState<Entry[]>([])
  const [nameSearch, setNameSearch] = useState('')
  const [fullTextSearch, setFullTextSearch] = useState('')
  const [showAdvancedSearch, setShowAdvancedSearch] = useState(false)
  const [typeFilter, setTypeFilter] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [limit, setLimit] = useState(50)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [importingEntry, setImportingEntry] = useState(false)
  const importEntryInputRef = useRef<HTMLInputElement | null>(null)

  const matchingActiveJournal =
    activeJournal && activeJournal.id === journalId ? activeJournal : null
  const currentWorkspaceId =
    matchingActiveJournal?.workspace_id
    ?? journals.find((journal) => journal.id === journalId)?.workspace_id
    ?? activeWorkspace?.id
  const currentJournalName =
    matchingActiveJournal?.name ?? journals.find((j) => j.id === journalId)?.name
  const currentJournalDescription =
    matchingActiveJournal?.description ?? journals.find((j) => j.id === journalId)?.description

  const hasSearchFilters = () => {
    if (nameSearch.trim()) return true
    if (showAdvancedSearch && fullTextSearch.trim()) return true
    if (showAdvancedSearch && typeFilter) return true
    if (showAdvancedSearch && fromDate) return true
    if (showAdvancedSearch && toDate) return true
    if (showAdvancedSearch && offset > 0) return true
    return false
  }

  const toStartOfDayIso = (value: string) => {
    if (!value) return undefined
    return `${value}T00:00:00.000Z`
  }

  const toEndOfDayIso = (value: string) => {
    if (!value) return undefined
    return `${value}T23:59:59.999Z`
  }

  const clearSearchFilters = () => {
    setNameSearch('')
    setFullTextSearch('')
    setTypeFilter('')
    setFromDate('')
    setToDate('')
    setLimit(50)
    setOffset(0)
  }

  const clearSearchAndReload = async () => {
    clearSearchFilters()
    if (!journalId) return
    setLoading(true)
    try {
      const r = await entriesApi.list(journalId)
      setEntries(r.data)
    } finally {
      setLoading(false)
    }
  }

  const load = async () => {
    if (!journalId) return
    setLoading(true)
    try {
      if (hasSearchFilters()) {
        const params = {
          journal_id: journalId,
          name: nameSearch.trim() || undefined,
          q: showAdvancedSearch ? (fullTextSearch.trim() || undefined) : undefined,
          entry_type: showAdvancedSearch ? (typeFilter || undefined) : undefined,
          from: showAdvancedSearch ? toStartOfDayIso(fromDate) : undefined,
          to: showAdvancedSearch ? toEndOfDayIso(toDate) : undefined,
          limit,
          offset,
        }
        const r = await entriesApi.search({
          ...params,
        })
        setEntries(r.data)
      } else {
        const r = await entriesApi.list(journalId)
        setEntries(r.data)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [journalId, location.key])

  const uniqueTypes = [...new Set(entries.flatMap((e) => e.tags))]

  const handleImportEntryPick = () => {
    if (!journalId) return
    importEntryInputRef.current?.click()
  }

  const handleImportEntryFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(event.target.files ?? [])
    event.target.value = ''

    if (!journalId || importingEntry || selectedFiles.length === 0) return

    const textFiles = selectedFiles.filter((file) => {
      const name = file.name.toLowerCase()
      return file.type === 'text/plain' || name.endsWith('.txt')
    })

    if (textFiles.length === 0) {
      window.alert('Select one .txt entry file, plus optional media files.')
      return
    }

    if (textFiles.length > 1) {
      window.alert('Please select only one .txt entry file per import.')
      return
    }

    const entryFile = textFiles[0]
    const mediaFiles = selectedFiles.filter((file) => file !== entryFile)

    setImportingEntry(true)
    try {
      const res = await dataManagementApi.importPlaintext(journalId, entryFile, mediaFiles)
      const errors = res.data.errors ?? []
      const message = errors.length > 0
        ? `${res.data.message}\n\nWarnings:\n${errors.join('\n')}`
        : res.data.message
      window.alert(message)
      navigate(`/journals/${journalId}`, {
        state: { refreshEntriesAt: Date.now() },
      })
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      const message = typeof detail === 'string' && detail.trim() ? detail : 'Entry import failed'
      window.alert(message)
    } finally {
      setImportingEntry(false)
    }
  }

  return (
    <div className={styles.page}>
      <h1 className={styles.journalTitle}>{currentJournalName ?? 'Journal'}</h1>
      {currentJournalDescription && (
        <p className={styles.journalDescription}>{currentJournalDescription}</p>
      )}
      <p className={styles.journalMeta}>
        {entries.length} entr{entries.length === 1 ? 'y' : 'ies'}
      </p>
      <div className={styles.toolbar}>
        <div className={styles.searchPanel}>
          <div className={styles.searchTopRow}>
            <input
              className="input"
              placeholder="Search by Entry Name"
              value={nameSearch}
              onChange={(e) => setNameSearch(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && load()}
            />
            <button
              className="btn btn-ghost"
              onClick={() => setShowAdvancedSearch((prev) => !prev)}
            >
              {showAdvancedSearch ? 'Hide Advanced Search' : 'Advanced Search'}
            </button>
            <button className="btn" onClick={load}>Search</button>
            <button
              className="btn btn-ghost"
              onClick={() => {
                void clearSearchAndReload()
              }}
            >
              Clear
            </button>
          </div>

          {showAdvancedSearch && (
            <div className={styles.advancedGrid}>
              <label className={styles.advancedField}>
                <span className={styles.advancedLabel}>Full-Text Query</span>
                <input
                  className="input"
                  placeholder="Search body/type/metadata"
                  value={fullTextSearch}
                  onChange={(e) => setFullTextSearch(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && load()}
                />
              </label>

              <label className={styles.advancedField}>
                <span className={styles.advancedLabel}>Entry Type</span>
                <select
                  className="input"
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value)}
                >
                  <option value="">All Types</option>
                  {uniqueTypes.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </label>

              <label className={styles.advancedField}>
                <span className={styles.advancedLabel}>From Date</span>
                <input
                  className="input"
                  type="date"
                  value={fromDate}
                  onChange={(e) => setFromDate(e.target.value)}
                />
              </label>

              <label className={styles.advancedField}>
                <span className={styles.advancedLabel}>To Date</span>
                <input
                  className="input"
                  type="date"
                  value={toDate}
                  onChange={(e) => setToDate(e.target.value)}
                />
              </label>

              <label className={styles.advancedField}>
                <span className={styles.advancedLabel}>Limit</span>
                <input
                  className="input"
                  type="number"
                  min={1}
                  max={200}
                  value={limit}
                  onChange={(e) => {
                    const value = Number(e.target.value)
                    if (!Number.isFinite(value)) return
                    setLimit(Math.max(1, Math.min(200, value)))
                  }}
                />
              </label>

              <label className={styles.advancedField}>
                <span className={styles.advancedLabel}>Offset</span>
                <input
                  className="input"
                  type="number"
                  min={0}
                  value={offset}
                  onChange={(e) => {
                    const value = Number(e.target.value)
                    if (!Number.isFinite(value)) return
                    setOffset(Math.max(0, value))
                  }}
                />
              </label>
            </div>
          )}
        </div>

        <div className={styles.rightActions}>
          <button className="btn btn-ghost" onClick={handleImportEntryPick} disabled={importingEntry}>
            {importingEntry ? 'Importing...' : 'Import Entry'}
          </button>
          <button
            className="btn"
            onClick={() => {
              const query = new URLSearchParams({ journal: journalId ?? '' })
              if (currentWorkspaceId) query.set('workspace', currentWorkspaceId)
              navigate(`/entries/new?${query.toString()}`)
            }}
          >
           ✦ Create Entry
          </button>
        </div>
        <input
          ref={importEntryInputRef}
          type="file"
          multiple
          accept=".txt,text/plain,image/*,video/*,audio/*"
          style={{ display: 'none' }}
          onChange={(e) => void handleImportEntryFile(e)}
        />
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
                navigate(`/entries/${entry.id}`, {
                  state: currentWorkspaceId ? { workspaceId: currentWorkspaceId } : undefined,
                })
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
              <span className={styles.entryTags}>
                {entry.tags.map((tag) => (
                  <span key={tag} className={styles.entryTag}>{tag}</span>
                ))}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
