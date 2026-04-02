import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import ReactQuill from 'react-quill-new'
import type { Delta } from 'quill'
import 'react-quill-new/dist/quill.snow.css'
import {
  type Entry,
  entriesApi,
  entryTypesApi,
  mediaApi,
  type EntryType,
  type MetadataField,
} from '../services/api'
import styles from './EntryEditor.module.css'

const editorQuill = (ReactQuill as unknown as { Quill: any }).Quill
const BaseBlockEmbed = editorQuill.import('blots/block/embed')

type AudioEmbedValue = {
  src: string
  original_filename?: string
}

type WebpageEmbedValue = {
  src: string
  source_url: string
  title: string
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
  if (!enabled) return [...withoutFlag, { key: SHOW_URLS_INLINE_KEY, value: 'false' }]
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
    const node = super.create() as HTMLElement
    node.setAttribute('data-src', value.src)
    node.setAttribute('data-source-url', value.source_url)
    node.setAttribute('data-title', value.title)
    node.setAttribute('contenteditable', 'false')

    const icon = document.createElement('div')
    icon.className = 'ql-webpage-icon'
    icon.textContent = '\u{1F310}'

    const info = document.createElement('div')
    info.className = 'ql-webpage-info'

    const titleEl = document.createElement('div')
    titleEl.className = 'ql-webpage-title'
    titleEl.textContent = value.title || value.source_url

    const urlEl = document.createElement('div')
    urlEl.className = 'ql-webpage-url'
    urlEl.textContent = value.source_url

    info.appendChild(titleEl)
    info.appendChild(urlEl)
    node.appendChild(icon)
    node.appendChild(info)
    return node
  }

  static value(node: HTMLElement): WebpageEmbedValue {
    return {
      src: node.getAttribute('data-src') ?? '',
      source_url: node.getAttribute('data-source-url') ?? '',
      title: node.getAttribute('data-title') ?? '',
    }
  }
}

if (!editorQuill.imports['formats/webpage']) {
  editorQuill.register(WebpageBlot)
}

export default function EntryEditor() {
  const { entryId } = useParams<{ entryId: string }>()
  const [searchParams] = useSearchParams()
  const journalId = searchParams.get('journal') ?? ''
  const navigate = useNavigate()

  const quillRef = useRef<ReactQuill>(null)

  const [entryTypes, setEntryTypes] = useState<EntryType[]>([])
  const [activeJournalId, setActiveJournalId] = useState(journalId)
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
  const showAudioInline = hasShowAudioInlineFlag(customMetadata)
  const showUrlsInline = hasShowUrlsInlineFlag(customMetadata)

  const getApiErrorMessage = (err: unknown, fallback: string) => {
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
  }, [journalId])

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
    entryTypesApi.list().then((r) => setEntryTypes(r.data))
  }, [entryId])

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

  const webpageHandler = async () => {
    const url = window.prompt('Enter webpage URL to save:')
    if (!url?.trim()) return
    const quill = quillRef.current?.getEditor()
    if (!quill) return
    const range = quill.getSelection(true)
    try {
      const res = await mediaApi.saveWebpage(url.trim())
      quill.insertEmbed(range.index, 'webpage', {
        src: res.data.resource_path,
        source_url: res.data.custom_metadata?.source_url ?? url.trim(),
        title: res.data.custom_metadata?.page_title ?? url.trim(),
      })
      quill.setSelection(range.index + 1, 0)
      setCustomMetadata((prev) => ensureShowUrlsInlineFlag(prev))
    } catch {
      alert('Failed to save webpage. Check the URL and try again.')
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
          ['link', 'image', 'video', 'webpage'],
          ['clean'],
        ],
        handlers: { image: imageHandler, webpage: webpageHandler },
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
    if (!selectedType.trim()) { setError('Entry type is required'); return }
    if (!journalId && !entryId) { setError('No journal selected'); return }

    setSaving(true)
    try {
      // Ensure type exists
      if (!entryTypes.find((t) => t.name === selectedType)) {
        await entryTypesApi.create(selectedType)
      }

      const payload = {
        type: selectedType,
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
      <div className={styles.header}>
        <div className={styles.typeRow}>
          <label className="label">Entry Type</label>
          <input
            className="input"
            list="entry-types-list"
            placeholder="e.g. Reflection, Dream, Travel…"
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value)}
            style={{ maxWidth: 280 }}
          />
          <datalist id="entry-types-list">
            {entryTypes.map((t) => (
              <option key={t.id} value={t.name} />
            ))}
          </datalist>
        </div>

        <div className={styles.typeRow}>
          <label className="label">
            Entry Name{' '}
            <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>(optional)</span>
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
                  className="btn btn-danger"
                  style={{ padding: '0.4rem 0.7rem' }}
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

        <section className={styles.linkPanel}>
          <div className={styles.linkPanelHeader}>
            <div>
              <p className={styles.linkPanelTitle}>Link another entry</p>
              <p className={styles.linkPanelHint}>
                Select text first to turn it into an internal entry link, or insert an entry title directly. Results stay in the current journal when possible.
              </p>
            </div>
            <button className="btn btn-ghost" type="button" onClick={toggleLinkPanel}>
              {showLinkPanel ? 'Hide' : 'Link Entry'}
            </button>
          </div>

          {showLinkPanel && (
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
          )}
        </section>
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
