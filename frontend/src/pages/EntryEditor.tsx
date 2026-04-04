import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import ReactQuill from 'react-quill-new'
import type { Delta } from 'quill'
import 'react-quill-new/dist/quill.snow.css'
import {
  type Entry,
  entriesApi,
  entryTypesApi,
  type MediaRecord,
  mediaApi,
  type EntryType,
  type MetadataField,
} from '../services/api'
import { useWorkspaceStore } from '../stores/workspaceStore'
import {
  getWebpageSourceLabel,
  listPendingWebpageResourcePaths,
  mediaToWebpageEmbed,
  syncWebpageEmbedsWithMedia,
  type WebpageEmbedValue,
} from '../utils/webpageEmbeds'
import styles from './EntryEditor.module.css'

const editorQuill = (ReactQuill as unknown as { Quill: any }).Quill
const BaseBlockEmbed = editorQuill.import('blots/block/embed')

type AudioEmbedValue = {
  src: string
  original_filename?: string
}

const SHOW_AUDIO_INLINE_KEY = 'show-audio-inline'
const SHOW_URLS_INLINE_KEY = 'show-urls-inline'

function formatEntryLinkLabel(entry: Pick<Entry, 'name' | 'date_created' | 'type'>): string {
  const trimmedName = entry.name?.trim()
  if (trimmedName) return trimmedName

  try {
    return new Date(entry.date_created).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return entry.type
  }
}

function isTruthyMetadataValue(value: string): boolean {
  return ['true', '1', 'yes', 'on'].includes(value.trim().toLowerCase())
}

function hasShowAudioInlineFlag(metadata: MetadataField[]): boolean {
  const field = metadata.find((meta) => meta.key === SHOW_AUDIO_INLINE_KEY)
  if (!field) return false
  return isTruthyMetadataValue(field.value)
}

function setShowAudioInlineFlag(metadata: MetadataField[], enabled: boolean): MetadataField[] {
  const withoutFlag = metadata.filter((meta) => meta.key !== SHOW_AUDIO_INLINE_KEY)
  if (!enabled) return withoutFlag
  return [...withoutFlag, { key: SHOW_AUDIO_INLINE_KEY, value: 'true' }]
}

function ensureShowUrlsInlineFlag(metadata: MetadataField[]): MetadataField[] {
  if (metadata.some((meta) => meta.key === SHOW_URLS_INLINE_KEY)) {
    return metadata
  }
  return [...metadata, { key: SHOW_URLS_INLINE_KEY, value: 'false' }]
}

function hasShowUrlsInlineFlag(metadata: MetadataField[]): boolean {
  const field = metadata.find((meta) => meta.key === SHOW_URLS_INLINE_KEY)
  if (!field) return false
  return isTruthyMetadataValue(field.value)
}

function setShowUrlsInlineFlag(metadata: MetadataField[], enabled: boolean): MetadataField[] {
  const withoutFlag = metadata.filter((meta) => meta.key !== SHOW_URLS_INLINE_KEY)
  if (!enabled) return withoutFlag
  return [...withoutFlag, { key: SHOW_URLS_INLINE_KEY, value: 'true' }]
}

class AudioBlot extends BaseBlockEmbed {
  static blotName = 'audio'
  static tagName = 'audio'
  static className = 'ql-audio-block'

  static create(value: string | AudioEmbedValue) {
    const src = typeof value === 'string' ? value : value.src
    const originalFilename = typeof value === 'string' ? '' : value.original_filename ?? ''
    const node = super.create() as HTMLAudioElement
    node.setAttribute('controls', '')
    node.setAttribute('preload', 'metadata')
    node.setAttribute('src', src)
    if (originalFilename) {
      node.setAttribute('data-original-filename', originalFilename)
    }
    return node
  }

  static value(node: HTMLAudioElement) {
    const src = node.getAttribute('src') ?? ''
    const originalFilename = node.getAttribute('data-original-filename') ?? ''
    if (!originalFilename) return src
    return {
      src,
      original_filename: originalFilename,
    }
  }
}

if (!editorQuill.imports['formats/audio']) {
  editorQuill.register(AudioBlot)
}

class WebpageBlot extends BaseBlockEmbed {
  static blotName = 'webpage'
  static tagName = 'div'
  static className = 'ql-webpage-block'

  static create(value: WebpageEmbedValue) {
    const status = value.status ?? 'completed'
    const node = super.create() as HTMLElement
    node.setAttribute('data-src', value.src)
    node.setAttribute('data-source-url', value.source_url)
    node.setAttribute('data-title', value.title)
    node.setAttribute('data-status', status)
    node.setAttribute('data-error-message', value.error_message ?? '')
    node.setAttribute('contenteditable', 'false')

    const icon = document.createElement('div')
    icon.className = 'ql-webpage-icon'
    icon.textContent = '\u{1F310}'

    const info = document.createElement('div')
    info.className = 'ql-webpage-info'

    const titleEl = document.createElement('div')
    titleEl.className = 'ql-webpage-title'
    titleEl.textContent = status === 'pending'
      ? 'Archiving webpage…'
      : value.title || getWebpageSourceLabel(value.source_url)

    const urlEl = document.createElement('div')
    urlEl.className = 'ql-webpage-url'
    urlEl.textContent = getWebpageSourceLabel(value.source_url)

    const statusEl = document.createElement('div')
    statusEl.className = 'ql-webpage-status'

    if (status === 'pending') {
      node.classList.add('ql-webpage-pending')
      statusEl.textContent = 'Archiving in background'
    } else if (status === 'failed') {
      node.classList.add('ql-webpage-failed')
      statusEl.textContent = value.error_message || 'Archive failed'
    }

    info.appendChild(titleEl)
    info.appendChild(urlEl)
    if (status === 'pending' || status === 'failed') {
      info.appendChild(statusEl)
    }
    node.appendChild(icon)
    node.appendChild(info)
    return node
  }

  static value(node: HTMLElement): WebpageEmbedValue {
    return {
      src: node.getAttribute('data-src') ?? '',
      source_url: node.getAttribute('data-source-url') ?? '',
      title: node.getAttribute('data-title') ?? '',
      status: (node.getAttribute('data-status') as WebpageEmbedValue['status']) ?? 'completed',
      error_message: node.getAttribute('data-error-message') || null,
    }
  }
}

if (!editorQuill.imports['formats/webpage']) {
  editorQuill.register(WebpageBlot)
}

export default function EntryEditor() {
  const { entryId } = useParams<{ entryId: string }>()
  const [searchParams] = useSearchParams()
  const location = useLocation()
  const journalId = searchParams.get('journal') ?? ''
  const workspaceParam = searchParams.get('workspace') ?? ''
  const locationWorkspaceId =
    ((location.state as { workspaceId?: string } | null)?.workspaceId ?? '')
  const navigate = useNavigate()
  const activeJournal = useWorkspaceStore((s) => s.activeJournal)
  const journals = useWorkspaceStore((s) => s.journals)

  const quillRef = useRef<ReactQuill>(null)
  const webpageArchiveInputRef = useRef<HTMLInputElement | null>(null)

  const [entryTypes, setEntryTypes] = useState<EntryType[]>([])
  const [activeJournalId, setActiveJournalId] = useState(journalId)
  const [activeWorkspaceId, setActiveWorkspaceId] = useState(
    workspaceParam || locationWorkspaceId,
  )
  const [selectedType, setSelectedType] = useState('')
  const [entryName, setEntryName] = useState('')
  const [customMetadata, setCustomMetadata] = useState<MetadataField[]>([])
  const [body, setBody] = useState<object>({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [showLinkPanel, setShowLinkPanel] = useState(false)
  const [linkQuery, setLinkQuery] = useState('')
  const [linkResults, setLinkResults] = useState<Entry[]>([])
  const [linkingEntries, setLinkingEntries] = useState(false)
  const [linkSearchError, setLinkSearchError] = useState('')
  const [linkResultsScope, setLinkResultsScope] = useState<'journal' | 'global' | null>(null)
  const [showWebpagePanel, setShowWebpagePanel] = useState(false)
  const [importingWebpage, setImportingWebpage] = useState(false)
  const [webpageUrl, setWebpageUrl] = useState('')
  const [archivingWebpage, setArchivingWebpage] = useState(false)
  const showAudioInline = hasShowAudioInlineFlag(customMetadata)
  const showUrlsInline = hasShowUrlsInlineFlag(customMetadata)
  const pendingWebpagePaths = useMemo(() => listPendingWebpageResourcePaths(body), [body])

  const getApiErrorMessage = (err: unknown, fallback: string, fieldLabels?: Record<string, string>) => {
    const detail = (err as { response?: { data?: { detail?: unknown; message?: unknown } } })
      ?.response?.data?.detail
    const message = (err as { response?: { data?: { detail?: unknown; message?: unknown } } })
      ?.response?.data?.message

    if (typeof detail === 'string' && detail.trim()) return detail
    if (Array.isArray(detail)) {
      const text = detail
        .map((item) => {
          if (typeof item === 'string') return item
          if (item && typeof item === 'object' && 'msg' in item) {
            const msg = (item as { msg?: unknown }).msg
            const loc = (item as { loc?: unknown[] }).loc
            const rawField = Array.isArray(loc) && loc.length > 1 ? String(loc[loc.length - 1]) : ''
            const field = rawField && fieldLabels?.[rawField] ? fieldLabels[rawField] : rawField
            if (typeof msg === 'string' && field) return `${field}: ${msg}`
            return typeof msg === 'string' ? msg : ''
          }
          return ''
        })
        .filter(Boolean)
        .join(', ')
      if (text) return text
    }

    if (typeof message === 'string' && message.trim()) return message
    return fallback
  }

  // Load existing entry when editing
  useEffect(() => {
    setActiveJournalId(journalId)
    if (workspaceParam || locationWorkspaceId) {
      setActiveWorkspaceId(workspaceParam || locationWorkspaceId)
    }
  }, [journalId, locationWorkspaceId, workspaceParam])

  useEffect(() => {
    if (activeWorkspaceId || !activeJournalId) return
    const matchingJournal =
      (activeJournal?.id === activeJournalId ? activeJournal : null)
      ?? journals.find((journal) => journal.id === activeJournalId)
    if (matchingJournal?.workspace_id) {
      setActiveWorkspaceId(matchingJournal.workspace_id)
    }
  }, [activeJournal, activeJournalId, activeWorkspaceId, journals])

  useEffect(() => {
    if (entryId) {
      entriesApi.get(entryId).then((r) => {
        setActiveJournalId(r.data.journal_id)
        setSelectedType(r.data.type)
        setEntryName(r.data.name)
        setCustomMetadata(r.data.custom_metadata)
        setBody(r.data.body)
      })
    }
  }, [entryId])

  useEffect(() => {
    if (!activeWorkspaceId) {
      setEntryTypes([])
      return
    }

    let isActive = true
    entryTypesApi.list(activeWorkspaceId)
      .then((response) => {
        if (!isActive) return
        setEntryTypes([...response.data].sort((left, right) => left.name.localeCompare(right.name)))
      })
      .catch(() => {
        if (!isActive) return
        setEntryTypes([])
      })

    return () => {
      isActive = false
    }
  }, [activeWorkspaceId])

  // Custom media handler: upload via backend, insert embed/link in editor
  const imageHandler = () => {
    const input = document.createElement('input')
    input.setAttribute('type', 'file')
    input.setAttribute('accept', 'image/*,video/*,audio/*')
    input.click()
    input.onchange = async () => {
      const file = input.files?.[0]
      if (!file || !quillRef.current) return
      const quill = quillRef.current.getEditor()
      const range = quill.getSelection(true)
      try {
        const res = await mediaApi.upload(file)
        const url = res.data.resource_path
        let insertedLength = 1
        if (res.data.media_type === 'video') {
          quill.insertEmbed(range.index, 'video', url)
        } else if (res.data.media_type === 'audio') {
          quill.insertEmbed(range.index, 'audio', {
            src: url,
            original_filename: res.data.original_filename || file.name,
          })
        } else {
          quill.insertEmbed(range.index, 'image', url)
        }
        quill.setSelection(range.index + insertedLength, 0)
      } catch {
        alert('Media upload failed.')
      }
    }
  }

  const webpageHandler = () => {
    setShowWebpagePanel((prev) => !prev)
  }

  const entryLinkHandler = () => {
    toggleLinkPanel()
  }

  const handleWebpageArchiveSelected = async (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return

    const quill = quillRef.current?.getEditor()
    if (!quill) return
    const range = quill.getSelection(true)

    setError('')
    setImportingWebpage(true)
    try {
      const res = await mediaApi.importWebpageArchive(file)
      quill.insertEmbed(
        range.index,
        'webpage',
        mediaToWebpageEmbed(res.data, { title: file.name }),
      )
      quill.setSelection(range.index + 1, 0)
      setCustomMetadata((prev) => ensureShowUrlsInlineFlag(prev))
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, 'Failed to import webpage archive.'))
    } finally {
      setImportingWebpage(false)
    }
  }

  useEffect(() => {
    if (pendingWebpagePaths.length === 0) return

    let cancelled = false
    let polling = false

    const pollPendingWebpages = async () => {
      if (polling) return
      polling = true

      try {
        const responses = await Promise.all(
          pendingWebpagePaths.map(async (resourcePath) => {
            try {
              return (await mediaApi.getStatus(resourcePath)).data
            } catch {
              return null
            }
          }),
        )

        if (cancelled) return

        const mediaByPath = new Map<string, MediaRecord>()
        for (const media of responses) {
          if (!media) continue
          mediaByPath.set(media.resource_path, media)
        }

        if (!mediaByPath.size) return
        setBody((currentBody) => syncWebpageEmbedsWithMedia(currentBody, mediaByPath))
      } finally {
        polling = false
      }
    }

    void pollPendingWebpages()
    const intervalId = window.setInterval(() => {
      void pollPendingWebpages()
    }, 2000)

    return () => {
      cancelled = true
      window.clearInterval(intervalId)
    }
  }, [pendingWebpagePaths])

  const handleArchiveWebpage = async () => {
    const normalizedUrl = webpageUrl.trim()
    if (!normalizedUrl) {
      setError('Enter a webpage URL first.')
      return
    }

    const quill = quillRef.current?.getEditor()
    if (!quill) return
    const range = quill.getSelection(true)

    setError('')
    setArchivingWebpage(true)
    try {
      const res = await mediaApi.saveWebpage(normalizedUrl)
      quill.insertEmbed(
        range.index,
        'webpage',
        mediaToWebpageEmbed(res.data, { source_url: normalizedUrl }),
      )
      quill.setSelection(range.index + 1, 0)
      setCustomMetadata((prev) => ensureShowUrlsInlineFlag(prev))
      setWebpageUrl('')
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, 'Failed to queue webpage archive.'))
    } finally {
      setArchivingWebpage(false)
    }
  }

  const searchLinkableEntries = async (query: string) => {
    setLinkSearchError('')
    setLinkingEntries(true)
    try {
      const searchParams = {
        q: query.trim() || undefined,
        limit: 8,
        offset: 0,
      }

      if (activeJournalId) {
        const journalRes = await entriesApi.search({
          ...searchParams,
          journal_id: activeJournalId,
        })
        const journalResults = journalRes.data.filter((entry) => entry.id !== entryId)

        if (journalResults.length > 0) {
          setLinkResults(journalResults)
          setLinkResultsScope('journal')
          return
        }
      }

      const globalRes = await entriesApi.search(searchParams)
      setLinkResults(globalRes.data.filter((entry) => entry.id !== entryId))
      setLinkResultsScope('global')
    } catch (err: unknown) {
      setLinkSearchError(getApiErrorMessage(err, 'Failed to search entries.'))
      setLinkResults([])
      setLinkResultsScope(null)
    } finally {
      setLinkingEntries(false)
    }
  }

  const toggleLinkPanel = () => {
    const nextValue = !showLinkPanel
    setShowLinkPanel(nextValue)
    if (nextValue) {
      void searchLinkableEntries(linkQuery)
    }
  }

  const handleLinkSearch = async () => {
    await searchLinkableEntries(linkQuery)
  }

  const insertEntryLink = (entry: Entry) => {
    const quill = quillRef.current?.getEditor()
    if (!quill) return

    const fallbackIndex = Math.max(0, quill.getLength() - 1)
    const range = quill.getSelection(true) ?? { index: fallbackIndex, length: 0 }
    const linkValue = `/entries/${entry.id}`

    if (range.length > 0) {
      quill.formatText(range.index, range.length, 'link', linkValue, 'user')
      quill.setSelection(range.index + range.length, 0, 'user')
    } else {
      const label = formatEntryLinkLabel(entry)
      quill.insertText(range.index, label, { link: linkValue }, 'user')
      quill.setSelection(range.index + label.length, 0, 'user')
    }

    setShowLinkPanel(false)
    setLinkSearchError('')
    setLinkResultsScope(null)
  }

  const modules = useMemo(
    () => ({
      toolbar: {
        container: [
          [{ header: [1, 2, 3, false] }],
          ['bold', 'italic', 'underline', 'strike'],
          ['blockquote', 'code-block'],
          [{ list: 'ordered' }, { list: 'bullet' }],
          ['link', 'image', 'video', 'webpage', 'entry-link'],
          ['clean'],
        ],
        handlers: { image: imageHandler, webpage: webpageHandler, 'entry-link': entryLinkHandler },
      },
    }),
    [],
  )

  const addMetaField = () =>
    setCustomMetadata((prev) => [...prev, { key: '', value: '' }])

  const updateMeta = (i: number, field: keyof MetadataField, val: string) =>
    setCustomMetadata((prev) =>
      prev.map((m, idx) => (idx === i ? { ...m, [field]: val } : m)),
    )

  const removeMeta = (i: number) =>
    setCustomMetadata((prev) => prev.filter((_, idx) => idx !== i))

  const save = async () => {
    setError('')
    const normalizedType = selectedType.trim()
    if (!normalizedType) { setError('Entry type is required'); return }
    if (!journalId && !entryId) { setError('No journal selected'); return }
    if (!activeWorkspaceId) { setError('No workspace selected'); return }

    setSaving(true)
    try {
      // Ensure type exists
      if (!entryTypes.find((t) => t.name === normalizedType)) {
        try {
          const createdEntryType = await entryTypesApi.create(activeWorkspaceId, normalizedType)
          setEntryTypes((prev) =>
            [...prev, createdEntryType.data].sort((left, right) => left.name.localeCompare(right.name)),
          )
        } catch (err: unknown) {
          setError(getApiErrorMessage(err, 'Failed to save. Please try again.', { name: 'entry type' }))
          setSaving(false)
          return
        }
      }

      const payload = {
        type: normalizedType,
        name: entryName.trim() || undefined,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || undefined,
        body,
        custom_metadata: customMetadata.filter((m) => m.key.trim()),
      }

      if (entryId) {
        await entriesApi.update(entryId, payload)
        navigate(`/entries/${entryId}`)
      } else {
        const r = await entriesApi.create(journalId, payload)
        navigate(`/entries/${r.data.id}`)
      }
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, 'Failed to save. Please try again.'))
    } finally {
      setSaving(false)
    }
  }

  const handleChange = (
    _value: string,
    _delta: Delta,
    _source: string,
    editor: ReactQuill.UnprivilegedEditor,
  ) => {
    setBody(editor.getContents())
  }

  return (
    <div className={styles.page}>
      <input
        ref={webpageArchiveInputRef}
        type="file"
        accept=".html,.htm,text/html"
        className={styles.hiddenFileInput}
        onChange={(event) => void handleWebpageArchiveSelected(event)}
      />

      <div className={styles.header}>
        <div className={styles.typeRow}>
          <label className="label">Entry Type</label>
          <div className={styles.typeControls}>
            <input
              className="input"
              list="entry-types-list"
              placeholder="e.g. Reflection, Dream, Travel…"
              value={selectedType}
              onChange={(e) => setSelectedType(e.target.value)}
              style={{ maxWidth: 280 }}
            />
          </div>
          <datalist id="entry-types-list">
            {entryTypes.map((t) => (
              <option key={t.id} value={t.name} />
            ))}
          </datalist>
        </div>

        <div className={styles.typeRow}>
          <label className="label">
            Entry Name
          </label>
          <input
            className="input"
            placeholder="Leave empty to auto-generate from date"
            value={entryName}
            onChange={(e) => setEntryName(e.target.value)}
            style={{ maxWidth: 320 }}
          />
        </div>

        <details className={styles.metaPanel}>
          <summary className={styles.metaSummary}>
            Custom fields ({customMetadata.length})
          </summary>
          <div className={styles.metaFields}>
            {customMetadata.map((m, i) => (
              <div key={i} className={styles.metaRow}>
                <input
                  className="input"
                  placeholder="Field name"
                  value={m.key}
                  onChange={(e) => updateMeta(i, 'key', e.target.value)}
                  style={{ maxWidth: 160 }}
                />
                <input
                  className="input"
                  placeholder="Value"
                  value={m.value}
                  onChange={(e) => updateMeta(i, 'value', e.target.value)}
                />
                <button
                  className={`btn btn-danger ${styles.metaRemoveBtn}`}
                  onClick={() => removeMeta(i)}
                >
                  ×
                </button>
              </div>
            ))}
            <button className="btn btn-ghost" onClick={addMetaField}>
              + Add field
            </button>
          </div>
        </details>

        <details className={styles.metaPanel}>
          <summary className={styles.metaSummary}>Preferences</summary>
          <div className={styles.prefsFields}>
            <label className={styles.checkboxRow}>
              <input
                type="checkbox"
                checked={showAudioInline}
                onChange={(e) =>
                  setCustomMetadata((prev) => setShowAudioInlineFlag(prev, e.target.checked))
                }
              />
              <span>Show audio inline in entry reader</span>
            </label>

            <label className={styles.checkboxRow}>
              <input
                type="checkbox"
                checked={showUrlsInline}
                onChange={(e) =>
                  setCustomMetadata((prev) => setShowUrlsInlineFlag(prev, e.target.checked))
                }
              />
              <span>Show webpages inline in entry reader</span>
            </label>
          </div>
        </details>

        {showWebpagePanel && (
          <section className={styles.webpageImportPanel}>
            <div className={styles.webpageImportCopy}>
              <p className={styles.webpageImportTitle}>Webpage Insert/Import</p>
              <p className={styles.webpageImportHint}>
                Add a URL to archive using SingleFile, or import from a saved SingleFile HTML archive.
              </p>
            </div>
            <div className={styles.webpageImportActions}>
              <div className={styles.webpageArchiveRow}>
                <input
                  className={`input ${styles.webpageUrlInput}`}
                  placeholder="https://example.com/article"
                  value={webpageUrl}
                  onChange={(event) => setWebpageUrl(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key !== 'Enter') return
                    event.preventDefault()
                    void handleArchiveWebpage()
                  }}
                />
                <button
                  className="btn"
                  type="button"
                  disabled={archivingWebpage || !webpageUrl.trim()}
                  onClick={() => void handleArchiveWebpage()}
                >
                  {archivingWebpage ? 'Adding…' : 'Add Link'}
                </button>
              </div>
              <button
                className="btn btn-ghost"
                type="button"
                disabled={importingWebpage}
                onClick={() => webpageArchiveInputRef.current?.click()}
              >
                {importingWebpage ? 'Importing…' : 'Import Saved HTML'}
              </button>
            </div>
          </section>
        )}

        {showLinkPanel && (
          <section className={styles.linkPanel}>
            <div className={styles.linkPanelHeader}>
              <div>
                <p className={styles.linkPanelTitle}>Link another entry</p>
                <p className={styles.linkPanelHint}>
                  Select text first to turn it into an internal entry link, or insert an entry title directly. Results stay in the current journal when possible.
                </p>
              </div>
            </div>

            <>
              <div className={styles.linkSearchRow}>
                <input
                  className={`input ${styles.linkSearchInput}`}
                  placeholder="Search entries by name or text"
                  value={linkQuery}
                  onChange={(e) => setLinkQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      void handleLinkSearch()
                    }
                  }}
                />
                <button
                  className="btn btn-ghost"
                  type="button"
                  onClick={() => void handleLinkSearch()}
                  disabled={linkingEntries}
                >
                  {linkingEntries ? 'Searching…' : 'Search'}
                </button>
              </div>

              {linkSearchError && <p className="error-text">{linkSearchError}</p>}

              {linkResultsScope === 'global' && activeJournalId && linkResults.length > 0 && (
                <p className={styles.linkStatus}>No matches in this journal. Showing results from your other entries.</p>
              )}

              <div className={styles.linkResults}>
                {!linkingEntries && linkResults.length === 0 && !linkSearchError && (
                  <p className={styles.linkStatus}>No matching entries found.</p>
                )}

                {linkResults.map((entry) => (
                  <article key={entry.id} className={styles.linkResult}>
                    <div className={styles.linkResultMeta}>
                      <p className={styles.linkResultTitle}>{formatEntryLinkLabel(entry)}</p>
                      <p className={styles.linkResultSubtitle}>
                        <span>{entry.type}</span>
                        <span>{new Date(entry.date_created).toLocaleDateString()}</span>
                      </p>
                    </div>
                    <button
                      className="btn btn-ghost"
                      type="button"
                      onClick={() => insertEntryLink(entry)}
                    >
                      Insert Link
                    </button>
                  </article>
                ))}
              </div>
            </>
          </section>
        )}
      </div>

      <div className={`paper ${styles.editorWrap}`}>
        <ReactQuill
          ref={quillRef}
          theme="snow"
          modules={modules}
          value={body as Delta}
          onChange={handleChange}
          placeholder="Begin writing…"
          className={styles.editor}
        />
      </div>

      {error && <p className="error-text">{error}</p>}

      <div className={styles.actions}>
        <button className="btn btn-ghost" onClick={() => navigate(-1)}>
          Cancel
        </button>
        <button className="btn" onClick={save} disabled={saving}>
          {saving ? 'Saving…' : 'Save Entry'}
        </button>
      </div>
    </div>
  )
}
