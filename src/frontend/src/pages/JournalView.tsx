import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { entriesApi, type Entry, type TagMode } from '../services/api'
import { entryThemeStyle } from '../utils/entryTheme'
import { useWorkspaceStore } from '../stores/workspaceStore'
import { fmtDate, fmtDateTimeTitle } from '../utils/datetime'
import styles from './JournalView.module.css'

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
  const [tagFilters, setTagFilters] = useState<string[]>([])
  const [tagMode, setTagMode] = useState<TagMode>('all')
  const [tagInput, setTagInput] = useState('')
  const [tagSuggestOpen, setTagSuggestOpen] = useState(false)
  const [activeTagSuggestion, setActiveTagSuggestion] = useState(-1)
  // Tags offered by the filter: taken from the unfiltered entry list, so the
  // options don't shrink as filters narrow the results.
  const [journalTags, setJournalTags] = useState<string[]>([])
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [limit, setLimit] = useState(50)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [creatingEntry, setCreatingEntry] = useState(false)
  const loadRequestRef = useRef(0)
  const tagInputRef = useRef<HTMLInputElement>(null)

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
    if (showAdvancedSearch && tagFilters.length > 0) return true
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
    setTagFilters([])
    setTagInput('')
    setFromDate('')
    setToDate('')
    setLimit(50)
    setOffset(0)
  }

  const load = async () => {
    if (!journalId) return
    const requestId = ++loadRequestRef.current
    setLoading(true)
    try {
      if (hasSearchFilters()) {
        const params = {
          journal_id: journalId,
          name: nameSearch.trim() || undefined,
          q: showAdvancedSearch ? (fullTextSearch.trim() || undefined) : undefined,
          tags: showAdvancedSearch && tagFilters.length > 0 ? tagFilters : undefined,
          tag_mode: tagMode,
          from_date: showAdvancedSearch ? toStartOfDayIso(fromDate) : undefined,
          to_date: showAdvancedSearch ? toEndOfDayIso(toDate) : undefined,
          limit,
          offset,
        }
        const r = await entriesApi.search({
          ...params,
        })
        // drop stale responses so a slow earlier keystroke can't overwrite newer results
        if (requestId !== loadRequestRef.current) return
        setEntries(r.data)
      } else {
        const r = await entriesApi.list(journalId)
        if (requestId !== loadRequestRef.current) return
        setEntries(r.data)
        setJournalTags([...new Set(r.data.flatMap((e) => e.tags))].sort((a, b) => a.localeCompare(b)))
      }
    } finally {
      if (requestId === loadRequestRef.current) setLoading(false)
    }
  }

  useEffect(() => { void load() }, [journalId, location.key])

  // Search-as-you-type over every filter (name and advanced), debounced. Skips
  // the first run because the effect above already does the initial load.
  const searchMountedRef = useRef(false)
  useEffect(() => {
    if (!searchMountedRef.current) {
      searchMountedRef.current = true
      return
    }
    const timer = window.setTimeout(() => { void load() }, 250)
    return () => window.clearTimeout(timer)
  }, [nameSearch, fullTextSearch, tagFilters, tagMode, fromDate, toDate, limit, offset, showAdvancedSearch])

  const tagSuggestions = journalTags.filter(
    (t) => !tagFilters.includes(t) && t.toLowerCase().includes(tagInput.trim().toLowerCase()),
  )
  const showTagSuggestions = tagSuggestOpen && tagSuggestions.length > 0

  const addTagFilter = (tag: string) => {
    if (!tagFilters.includes(tag)) setTagFilters([...tagFilters, tag])
    setTagInput('')
    setActiveTagSuggestion(-1)
  }

  const removeTagFilter = (tag: string) => {
    setTagFilters(tagFilters.filter((t) => t !== tag))
  }

  const handleTagKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown' && tagSuggestions.length > 0) {
      e.preventDefault()
      setTagSuggestOpen(true)
      setActiveTagSuggestion((i) => (i + 1) % tagSuggestions.length)
    } else if (e.key === 'ArrowUp' && tagSuggestions.length > 0) {
      e.preventDefault()
      setActiveTagSuggestion((i) => (i <= 0 ? tagSuggestions.length - 1 : i - 1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      // Only existing tags can be filtered on: take the highlighted suggestion,
      // else an exact (case-insensitive) match, else the sole remaining match.
      const typed = tagInput.trim().toLowerCase()
      const pick =
        (activeTagSuggestion >= 0 ? tagSuggestions[activeTagSuggestion] : undefined)
        ?? tagSuggestions.find((t) => t.toLowerCase() === typed)
        ?? (typed && tagSuggestions.length === 1 ? tagSuggestions[0] : undefined)
      if (pick) addTagFilter(pick)
    } else if (e.key === 'Escape') {
      setTagSuggestOpen(false)
      setActiveTagSuggestion(-1)
    } else if (e.key === 'Backspace' && !tagInput && tagFilters.length > 0) {
      removeTagFilter(tagFilters[tagFilters.length - 1])
    }
  }

  const handleCreateEntry = async () => {
    if (!journalId || creatingEntry) return
    setCreatingEntry(true)
    try {
      const res = await entriesApi.create(journalId, { tags: [], body: '', custom_metadata: [] })
      const query = new URLSearchParams({ journal: journalId })
      if (currentWorkspaceId) query.set('workspace', currentWorkspaceId)
      navigate(`/entries/${res.data.id}/edit`)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      const message = typeof detail === 'string' && detail.trim() ? detail : 'Failed to create entry'
      window.alert(message)
    } finally {
      setCreatingEntry(false)
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
            <button className="btn btn-ghost" onClick={clearSearchFilters}>
              Clear
            </button>
          </div>

          {showAdvancedSearch && (
            <div className={styles.advancedGrid}>
              <label className={styles.advancedField}>
                <span className={styles.advancedLabel}>Full-Text Query</span>
                <input
                  className="input"
                  placeholder="Search entry text"
                  value={fullTextSearch}
                  onChange={(e) => setFullTextSearch(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && load()}
                />
              </label>

              <div className={`${styles.advancedField} ${styles.tagField}`}>
                <div className={styles.tagLabelRow}>
                  <span className={styles.advancedLabel}>Tags</span>
                  <div className={styles.tagModeToggle} role="radiogroup" aria-label="Tag match mode">
                    {([['all', 'All', 'Entries must have every selected tag'],
                       ['any', 'Any', 'Entries need at least one selected tag']] as const).map(([mode, label, title]) => (
                      <button key={mode} type="button" role="radio" aria-checked={tagMode === mode} title={title}
                        className={`${styles.tagModeBtn}${tagMode === mode ? ` ${styles.tagModeBtnActive}` : ''}`}
                        onClick={() => setTagMode(mode)}>
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className={styles.tagInputWrap}>
                  <div className={styles.tagChips} onClick={() => tagInputRef.current?.focus()}>
                    {tagFilters.map((tag) => (
                      <span key={tag} className={styles.tagChip}>
                        {tag}
                        <button type="button" className={styles.tagChipRemove}
                          onClick={() => removeTagFilter(tag)} aria-label={`Remove tag filter ${tag}`}>×</button>
                      </span>
                    ))}
                    <input ref={tagInputRef} className={styles.tagChipInput}
                      role="combobox"
                      aria-label="Filter by tag"
                      aria-autocomplete="list"
                      aria-expanded={showTagSuggestions}
                      aria-controls="tag-filter-suggestions"
                      aria-activedescendant={showTagSuggestions && activeTagSuggestion >= 0
                        ? `tag-filter-suggestion-${activeTagSuggestion}` : undefined}
                      placeholder={tagFilters.length === 0 ? 'All tags' : 'Add tag…'}
                      value={tagInput}
                      onChange={(e) => { setTagInput(e.target.value); setTagSuggestOpen(true); setActiveTagSuggestion(-1) }}
                      onFocus={() => setTagSuggestOpen(true)}
                      onKeyDown={handleTagKeyDown}
                      onBlur={() => { setTagSuggestOpen(false); setActiveTagSuggestion(-1) }} />
                  </div>
                  {showTagSuggestions && (
                    <ul id="tag-filter-suggestions" role="listbox" className={styles.tagSuggestions}>
                      {tagSuggestions.map((tag, i) => (
                        <li key={tag} id={`tag-filter-suggestion-${i}`} role="option"
                          aria-selected={i === activeTagSuggestion}
                          className={`${styles.tagSuggestion}${i === activeTagSuggestion ? ` ${styles.tagSuggestionActive}` : ''}`}
                          // mousedown + preventDefault keeps focus in the input (no blur first)
                          onMouseDown={(e) => { e.preventDefault(); addTagFilter(tag) }}>
                          {tag}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>

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
          <button
            className="btn"
            onClick={() => void handleCreateEntry()}
            disabled={creatingEntry}
          >
            {creatingEntry ? 'Creating...' : '✦ Create Entry'}
          </button>
        </div>
      </div>

      {loading ? (
        <p className={styles.hint}>Loading…</p>
      ) : entries.length === 0 ? (
        <p className={styles.hint}>
          {hasSearchFilters() ? 'No entries match these filters.' : 'No entries yet. Create one!'}
        </p>
      ) : (
        <div className={styles.list}>
          {entries.sort((a, b) => new Date(b.date_created).getTime() - new Date(a.date_created).getTime())
            .map((entry) => (
              <button
                key={entry.id}
                className={`paper ${styles.entryRow}`}
                style={entryThemeStyle(entry.theme, { autoTextOnly: true })}
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
