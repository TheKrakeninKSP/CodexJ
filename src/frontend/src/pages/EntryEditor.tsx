import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import ImageExt from '@tiptap/extension-image'
import LinkExt from '@tiptap/extension-link'
import Underline from '@tiptap/extension-underline'
import Placeholder from '@tiptap/extension-placeholder'
import {
  type Entry,
  type EntryUpdate,
  type EntryTheme,
  entriesApi,
  tagsApi,
  type MediaRecord,
  mediaApi,
  type Tag,
  type MetadataField,
} from '../services/api'
import { getApiErrorMessage } from '../utils/errors'
import { getCurrentTimeZone, isoToLocalDateTime } from '../utils/datetime'
import { useWorkspaceStore } from '../stores/workspaceStore'
import { useEditorPrefsStore, CONTENT_WIDTH_MAP } from '../stores/editorPrefsStore'
import {
  listPendingWebpageMediaIds,
  mediaToWebpageEmbed,
} from '../utils/webpageEmbeds'
import { deltaToHtml } from '../utils/deltaToHtml'
import {
  TRACK_VERSIONS_KEY,
  hasTrackVersionsFlag,
  setTrackVersionsFlag,
} from '../utils/versionDiff'
import { AudioNode } from '../extensions/AudioNode'
import { PdfNode } from '../extensions/PdfNode'
import { VideoNode } from '../extensions/VideoNode'
import { WebpageNode } from '../extensions/WebpageNode'
import styles from './EntryEditor.module.css'

const SHOW_AUDIO_INLINE_KEY = 'show-audio-inline'
const SHOW_URLS_INLINE_KEY = 'show-urls-inline'
const IDENTIFY_AUDIO_KEY = 'identify-audio'
const HIDE_BG_AUDIO_KEY = 'hide-bg-audio'

function extractAudioMediaIds(body: string): string[] {
  if (typeof body !== 'string') return []
  const doc = new DOMParser().parseFromString(body, 'text/html')
  const ids: string[] = []
  const seen = new Set<string>()
  for (const el of doc.querySelectorAll('audio[data-media-id]')) {
    const id = el.getAttribute('data-media-id')
    if (id && !seen.has(id)) { seen.add(id); ids.push(id) }
  }
  return ids
}

function formatEntryLinkLabel(entry: Pick<Entry, 'name' | 'date_created' | 'tags'>): string {
  const trimmedName = entry.name?.trim()
  if (trimmedName) return trimmedName
  try {
    return new Date(entry.date_created).toLocaleDateString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
    })
  } catch {
    return entry.tags[0] ?? ''
  }
}

function isTruthyMetadataValue(value: string): boolean {
  return ['true', '1', 'yes', 'on'].includes(value.trim().toLowerCase())
}

function hasShowAudioInlineFlag(metadata: MetadataField[]): boolean {
  const field = metadata.find((m) => m.key === SHOW_AUDIO_INLINE_KEY)
  return field ? isTruthyMetadataValue(field.value) : false
}

function setShowAudioInlineFlag(metadata: MetadataField[], enabled: boolean): MetadataField[] {
  const without = metadata.filter((m) => m.key !== SHOW_AUDIO_INLINE_KEY)
  return enabled ? [...without, { key: SHOW_AUDIO_INLINE_KEY, value: 'true' }] : without
}

function ensureShowUrlsInlineFlag(metadata: MetadataField[]): MetadataField[] {
  if (metadata.some((m) => m.key === SHOW_URLS_INLINE_KEY)) return metadata
  return [...metadata, { key: SHOW_URLS_INLINE_KEY, value: 'false' }]
}

function hasShowUrlsInlineFlag(metadata: MetadataField[]): boolean {
  const field = metadata.find((m) => m.key === SHOW_URLS_INLINE_KEY)
  return field ? isTruthyMetadataValue(field.value) : false
}

function setShowUrlsInlineFlag(metadata: MetadataField[], enabled: boolean): MetadataField[] {
  const without = metadata.filter((m) => m.key !== SHOW_URLS_INLINE_KEY)
  return enabled ? [...without, { key: SHOW_URLS_INLINE_KEY, value: 'true' }] : without
}

function hasIdentifyAudioFlag(metadata: MetadataField[]): boolean {
  const field = metadata.find((m) => m.key === IDENTIFY_AUDIO_KEY)
  return field ? isTruthyMetadataValue(field.value) : false
}

function setIdentifyAudioFlag(metadata: MetadataField[], enabled: boolean): MetadataField[] {
  const without = metadata.filter((m) => m.key !== IDENTIFY_AUDIO_KEY)
  return enabled ? [...without, { key: IDENTIFY_AUDIO_KEY, value: 'true' }] : without
}

function hasHideBgAudioFlag(metadata: MetadataField[]): boolean {
  const field = metadata.find((m) => m.key === HIDE_BG_AUDIO_KEY)
  return field ? isTruthyMetadataValue(field.value) : false
}

function setHideBgAudioFlag(metadata: MetadataField[], enabled: boolean): MetadataField[] {
  const without = metadata.filter((m) => m.key !== HIDE_BG_AUDIO_KEY)
  return enabled ? [...without, { key: HIDE_BG_AUDIO_KEY, value: 'true' }] : without
}

// ── Toolbar button ─────────────────────────────────────────────────────────────

interface ToolbarBtnProps {
  active?: boolean
  disabled?: boolean
  title: string
  onClick: () => void
  children: React.ReactNode
}

function ToolbarBtn({ active, disabled, title, onClick, children }: ToolbarBtnProps) {
  return (
    <button
      type="button"
      className={`${styles.toolbarBtn}${active ? ` ${styles.toolbarBtnActive}` : ''}`}
      disabled={disabled}
      title={title}
      onMouseDown={(e) => { e.preventDefault(); onClick() }}
    >
      {children}
    </button>
  )
}

// ── Main component ─────────────────────────────────────────────────────────────

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

  const webpageArchiveInputRef = useRef<HTMLInputElement | null>(null)
  const bgAudioInputRef = useRef<HTMLInputElement | null>(null)
  const mediaInputRef = useRef<HTMLInputElement | null>(null)
  const tagInputRef = useRef<HTMLInputElement | null>(null)

  const { contentWidth, stickyToolbar } = useEditorPrefsStore()

  const [entryTypes, setEntryTypes] = useState<Tag[]>([])
  const [activeJournalId, setActiveJournalId] = useState(journalId)
  const [activeWorkspaceId, setActiveWorkspaceId] = useState(
    workspaceParam || locationWorkspaceId,
  )
  const [selectedTags, setSelectedTags] = useState<string[]>([])
  const [tagInput, setTagInput] = useState('')
  const [entryName, setEntryName] = useState('')
  const [customMetadata, setCustomMetadata] = useState<MetadataField[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [useCustomDate, setUseCustomDate] = useState(false)
  const [customDate, setCustomDate] = useState('')
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
  const [pendingMusicLookup, setPendingMusicLookup] = useState(false)
  const [entryTheme, setEntryTheme] = useState<EntryTheme>({})
  const [bgAudioMedia, setBgAudioMedia] = useState<MediaRecord | null>(null)
  const [uploadingBgAudio, setUploadingBgAudio] = useState(false)
  const [initialContent, setInitialContent] = useState<string | null>(null)

  const showAudioInline = hasShowAudioInlineFlag(customMetadata)
  const showUrlsInline = hasShowUrlsInlineFlag(customMetadata)
  const identifyAudio = hasIdentifyAudioFlag(customMetadata)
  const hideBgAudio = hasHideBgAudioFlag(customMetadata)
  const trackVersions = hasTrackVersionsFlag(customMetadata)

  const editor = useEditor({
    extensions: [
      StarterKit,
      ImageExt,
      LinkExt.configure({ openOnClick: false }),
      Underline,
      Placeholder.configure({ placeholder: 'Begin writing…' }),
      AudioNode,
      PdfNode,
      VideoNode,
      WebpageNode,
    ],
    content: initialContent ?? '',
    editorProps: {
      handleDrop: (view, event, _slice, moved) => {
        if (moved) return false
        const files = Array.from(event.dataTransfer?.files ?? []).filter(
          (f) =>
            f.type.startsWith('image/') ||
            f.type.startsWith('video/') ||
            f.type.startsWith('audio/') ||
            f.type === 'application/pdf',
        )
        if (files.length === 0 || !entryId) return false
        event.preventDefault()
        const { pos } = view.posAtCoords({ left: event.clientX, top: event.clientY }) ?? { pos: 0 }
        void handleDropFiles(files, pos)
        return true
      },
    },
  })

  // Track body as HTML string, synced from editor
  const bodyRef = useRef<string>(initialContent ?? '')
  useEffect(() => {
    if (!editor) return
    const handler = () => { bodyRef.current = editor.getHTML() }
    editor.on('update', handler)
    return () => { editor.off('update', handler) }
  }, [editor])

  // Pending webpage media ids — scanned from the live editor HTML
  const [pendingWebpageMediaIds, setPendingWebpageMediaIds] = useState<string[]>([])
  useEffect(() => {
    if (!editor) return
    const scan = () => {
      setPendingWebpageMediaIds(listPendingWebpageMediaIds(editor.getHTML()))
    }
    editor.on('update', scan)
    return () => { editor.off('update', scan) }
  }, [editor])

  // Load existing entry
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
      ?? journals.find((j) => j.id === activeJournalId)
    if (matchingJournal?.workspace_id) {
      setActiveWorkspaceId(matchingJournal.workspace_id)
    }
  }, [activeJournal, activeJournalId, activeWorkspaceId, journals])

  useEffect(() => {
    if (!entryId) return
    entriesApi.get(entryId).then((r) => {
      setActiveJournalId(r.data.journal_id)
      setSelectedTags(r.data.tags)
      setEntryName(r.data.name ?? '')
      setCustomMetadata(r.data.custom_metadata)
      setCustomDate(isoToLocalDateTime(r.data.date_created))

      const rawBody = r.data.body as unknown
      const html = typeof rawBody === 'string' ? rawBody : deltaToHtml(rawBody)
      setInitialContent(html)
      bodyRef.current = html

      if (r.data.theme) {
        setEntryTheme(r.data.theme)
        if (r.data.theme.audio) {
          mediaApi.getStatus(r.data.theme.audio)
            .then((mr) => setBgAudioMedia(mr.data))
            .catch(() => {})
        }
      }
    })
  }, [entryId])

  // When initialContent arrives, load it into the editor
  useEffect(() => {
    if (initialContent === null || !editor) return
    editor.commands.setContent(initialContent)
    bodyRef.current = initialContent
    setPendingWebpageMediaIds(listPendingWebpageMediaIds(initialContent))
  }, [initialContent, editor])

  useEffect(() => {
    if (!activeWorkspaceId) { setEntryTypes([]); return }
    let active = true
    tagsApi.list()
      .then((r) => { if (active) setEntryTypes([...r.data].sort((a, b) => a.name.localeCompare(b.name))) })
      .catch(() => { if (active) setEntryTypes([]) })
    return () => { active = false }
  }, [activeWorkspaceId])

  // Poll pending webpage archives
  useEffect(() => {
    if (pendingWebpageMediaIds.length === 0 || !editor) return
    let cancelled = false
    let polling = false

    const poll = async () => {
      if (polling) return
      polling = true
      try {
        const responses = await Promise.all(
          pendingWebpageMediaIds.map(async (mediaId) => {
            try { return (await mediaApi.getStatus(mediaId)).data } catch { return null }
          }),
        )
        if (cancelled) return
        const mediaById = new Map<string, MediaRecord>()
        for (const m of responses) { if (m) mediaById.set(m.id, m) }
        if (!mediaById.size) return
        for (const [mediaId, media] of mediaById) {
          const embed = mediaToWebpageEmbed(media)
          editor.commands.updateWebpageByMediaId(mediaId, {
            src: embed.src,
            sourceUrl: embed.source_url,
            title: embed.title,
            status: embed.status,
            errorMessage: embed.error_message,
          })
        }
      } finally { polling = false }
    }

    void poll()
    const id = window.setInterval(() => { void poll() }, 2000)
    return () => { cancelled = true; window.clearInterval(id) }
  }, [pendingWebpageMediaIds, editor])

  // ── Media upload ─────────────────────────────────────────────────────────────

  const handleDropFiles = useCallback(async (files: File[], insertPos?: number) => {
    if (!editor || !entryId) return
    for (const file of files) {
      try {
        const res = await mediaApi.upload(entryId, file)
        const url = res.data.resource_path

        if (res.data.media_type === 'audio') {
          editor.commands.insertAudio({
            src: url,
            originalFilename: res.data.original_filename || file.name,
            mediaId: res.data.id,
          })
          setEntryTheme((prev) => ({ ...prev, audio: res.data.id }))
          setBgAudioMedia(res.data)
          setCustomMetadata((prev) => setIdentifyAudioFlag(prev, true))
          setPendingMusicLookup(true)
          continue
        }

        let content: object
        if (res.data.media_type === 'video') {
          content = { type: 'video', attrs: { src: url } }
        } else if (res.data.media_type === 'pdf') {
          content = { type: 'pdf', attrs: { src: url } }
        } else {
          content = { type: 'image', attrs: { src: url } }
        }

        const chain = editor.chain().focus()
        if (insertPos !== undefined) {
          chain.insertContentAt(insertPos, content)
        } else {
          chain.insertContent(content)
        }
        chain.run()
      } catch {
        alert('Media upload failed.')
      }
    }
  }, [editor, entryId])

  const handleMediaInputChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (file) await handleDropFiles([file])
  }

  const handleBgAudioUpload = async (file: File) => {
    if (!entryId) return
    setUploadingBgAudio(true)
    try {
      const res = await mediaApi.upload(entryId, file)
      setEntryTheme((prev) => ({ ...prev, audio: res.data.id }))
      setBgAudioMedia(res.data)
      editor?.commands.insertAudio({
        src: res.data.resource_path,
        originalFilename: res.data.original_filename || file.name,
        mediaId: res.data.id,
      })
      setCustomMetadata((prev) => setHideBgAudioFlag(prev, true))
      setCustomMetadata((prev) => setIdentifyAudioFlag(prev, true))
      setPendingMusicLookup(true)
    } catch {
      setError('Background audio upload failed.')
    } finally {
      setUploadingBgAudio(false)
    }
  }

  const handleWebpageArchiveSelected = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || !entryId || !editor) return
    setError('')
    setImportingWebpage(true)
    try {
      const res = await mediaApi.importWebpageArchive(entryId, file)
      const embed = mediaToWebpageEmbed(res.data, { title: file.name })
      editor.commands.insertWebpage({
        src: embed.src,
        sourceUrl: embed.source_url,
        title: embed.title,
        status: embed.status,
        errorMessage: embed.error_message,
        mediaId: embed.media_id,
      })
      setCustomMetadata((prev) => ensureShowUrlsInlineFlag(prev))
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, 'Failed to import webpage archive.'))
    } finally {
      setImportingWebpage(false)
    }
  }

  const handleArchiveWebpage = async () => {
    const url = webpageUrl.trim()
    if (!url) { setError('Enter a webpage URL first.'); return }
    if (!entryId || !editor) return
    setError('')
    setArchivingWebpage(true)
    try {
      const res = await mediaApi.saveWebpage(entryId, url)
      const embed = mediaToWebpageEmbed(res.data, { source_url: url })
      editor.commands.insertWebpage({
        src: embed.src,
        sourceUrl: embed.source_url,
        title: embed.title,
        status: embed.status,
        errorMessage: embed.error_message,
        mediaId: embed.media_id,
      })
      setCustomMetadata((prev) => ensureShowUrlsInlineFlag(prev))
      setWebpageUrl('')
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, 'Failed to queue webpage archive.'))
    } finally {
      setArchivingWebpage(false)
    }
  }

  // ── Link panel ────────────────────────────────────────────────────────────────

  const searchLinkableEntries = async (query: string) => {
    setLinkSearchError('')
    setLinkingEntries(true)
    try {
      const params = { q: query.trim() || undefined, limit: 8, offset: 0 }
      if (activeJournalId) {
        const res = await entriesApi.search({ ...params, journal_id: activeJournalId })
        const results = res.data.filter((e) => e.id !== entryId)
        if (results.length > 0) {
          setLinkResults(results); setLinkResultsScope('journal'); return
        }
      }
      const res = await entriesApi.search(params)
      setLinkResults(res.data.filter((e) => e.id !== entryId))
      setLinkResultsScope('global')
    } catch (err: unknown) {
      setLinkSearchError(getApiErrorMessage(err, 'Failed to search entries.'))
      setLinkResults([]); setLinkResultsScope(null)
    } finally {
      setLinkingEntries(false) }
  }

  const toggleLinkPanel = () => {
    setShowLinkPanel((prev) => {
      if (!prev) void searchLinkableEntries(linkQuery)
      return !prev
    })
  }

  const insertEntryLink = (entry: Entry) => {
    if (!editor) return
    const href = `/entries/${entry.id}`
    const { from, to } = editor.state.selection
    if (from !== to) {
      editor.chain().focus().setLink({ href }).run()
    } else {
      const label = formatEntryLinkLabel(entry)
      editor.chain().focus().insertContent(`<a href="${href}">${label}</a>`).run()
    }
    setShowLinkPanel(false)
    setLinkSearchError('')
    setLinkResultsScope(null)
  }

  // ── Metadata / tag helpers ────────────────────────────────────────────────────

  const addMetaField = () => setCustomMetadata((prev) => [...prev, { key: '', value: '' }])
  const updateMeta = (i: number, field: keyof MetadataField, val: string) =>
    setCustomMetadata((prev) => prev.map((m, idx) => (idx === i ? { ...m, [field]: val } : m)))
  const removeMeta = (i: number) =>
    setCustomMetadata((prev) => prev.filter((_, idx) => idx !== i))

  const addTag = (raw: string) => {
    const trimmed = raw.trim()
    if (!trimmed) return
    setSelectedTags((prev) => prev.includes(trimmed) ? prev : [...prev, trimmed])
    setTagInput('')
  }
  const removeTag = (tag: string) => setSelectedTags((prev) => prev.filter((t) => t !== tag))
  const handleTagKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addTag(tagInput) }
    else if (e.key === 'Backspace' && !tagInput && selectedTags.length > 0) {
      setSelectedTags((prev) => prev.slice(0, -1))
    }
  }

  // ── Save ──────────────────────────────────────────────────────────────────────

  const save = async () => {
    setError('')
    if (!entryId) { setError('No entry to save'); return }
    if (!activeWorkspaceId) { setError('No workspace selected'); return }
    const pendingTag = tagInput.trim()
    const finalTags = pendingTag && !selectedTags.includes(pendingTag)
      ? [...selectedTags, pendingTag] : selectedTags

    setSaving(true)
    try {
      for (const tag of finalTags) {
        if (!entryTypes.find((t) => t.name === tag)) {
          try {
            const created = await tagsApi.create(tag)
            setEntryTypes((prev) => [...prev, created.data].sort((a, b) => a.name.localeCompare(b.name)))
          } catch (err: unknown) {
            setError(getApiErrorMessage(err, 'Failed to save. Please try again.', { name: 'tag' }))
            setSaving(false); return
          }
        }
      }

      const body = editor ? editor.getHTML() : bodyRef.current
      const payload: EntryUpdate = {
        tags: finalTags,
        name: entryName.trim(),
        timezone: getCurrentTimeZone(),
        body,
        custom_metadata: customMetadata.filter((m) => m.key.trim()),
        theme: {
          bg_color: entryTheme.bg_color ?? null,
          font_color: entryTheme.font_color ?? null,
          audio: entryTheme.audio ?? null,
        },
      }
      if (useCustomDate && customDate) {
        payload.date_created = new Date(customDate).toISOString()
      }

      await entriesApi.update(entryId, payload)

      if (pendingMusicLookup) {
        const mediaIds = extractAudioMediaIds(body)
        if (mediaIds.length > 0) {
          void Promise.all(mediaIds.map((id) => mediaApi.identifyMusic(id).catch(() => {})))
        }
        setPendingMusicLookup(false)
      }
      navigate(`/entries/${entryId}`)
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, 'Failed to save. Please try again.'))
    } finally {
      setSaving(false)
    }
  }

  // ── Toolbar helpers ───────────────────────────────────────────────────────────

  const isActive = useMemo(() => ({
    bold: () => editor?.isActive('bold') ?? false,
    italic: () => editor?.isActive('italic') ?? false,
    underline: () => editor?.isActive('underline') ?? false,
    strike: () => editor?.isActive('strike') ?? false,
    h1: () => editor?.isActive('heading', { level: 1 }) ?? false,
    h2: () => editor?.isActive('heading', { level: 2 }) ?? false,
    h3: () => editor?.isActive('heading', { level: 3 }) ?? false,
    blockquote: () => editor?.isActive('blockquote') ?? false,
    codeBlock: () => editor?.isActive('codeBlock') ?? false,
    orderedList: () => editor?.isActive('orderedList') ?? false,
    bulletList: () => editor?.isActive('bulletList') ?? false,
    link: () => editor?.isActive('link') ?? false,
  }), [editor])

  return (
    <div className={styles.page} style={{ maxWidth: CONTENT_WIDTH_MAP[contentWidth] }}>
      <input ref={webpageArchiveInputRef} type="file" accept=".html,.htm,text/html"
        className={styles.hiddenFileInput}
        onChange={(e) => void handleWebpageArchiveSelected(e)} />
      <input ref={bgAudioInputRef} type="file" accept="audio/*"
        className={styles.hiddenFileInput}
        onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) void handleBgAudioUpload(f) }} />
      <input ref={mediaInputRef} type="file"
        accept="image/*,video/*,audio/*,application/pdf"
        className={styles.hiddenFileInput}
        onChange={(e) => void handleMediaInputChange(e)} />

      <div className={styles.header}>
        <div className={styles.typeRow}>
          <label className="label">Tags</label>
          <div className={styles.tagInputWrap}>
            <div className={styles.tagChips}>
              {selectedTags.map((tag) => (
                <span key={tag} className={styles.tagChip}>
                  {tag}
                  <button type="button" className={styles.tagChipRemove}
                    onClick={() => removeTag(tag)} aria-label={`Remove tag ${tag}`}>×</button>
                </span>
              ))}
              <input ref={tagInputRef} className={`input ${styles.tagChipInput}`}
                list="entry-types-list"
                placeholder={selectedTags.length === 0 ? 'e.g. Reflection, Dream…' : 'Add tag…'}
                value={tagInput}
                onChange={(e) => setTagInput(e.target.value)}
                onKeyDown={handleTagKeyDown}
                onBlur={() => { if (tagInput.trim()) addTag(tagInput) }} />
            </div>
            <datalist id="entry-types-list">
              {entryTypes.filter((t) => !selectedTags.includes(t.name)).map((t) => (
                <option key={t.id} value={t.name} />
              ))}
            </datalist>
          </div>
        </div>

        <div className={styles.typeRow}>
          <label className="label">Entry Name</label>
          <input className="input" placeholder="Leave empty to auto-generate from date"
            value={entryName} onChange={(e) => setEntryName(e.target.value)}
            style={{ maxWidth: 320 }} />
        </div>

        <details className={styles.metaPanel}>
          <summary className={styles.metaSummary}>Custom fields ({customMetadata.length})</summary>
          <div className={styles.metaFields}>
            {customMetadata.map((m, i) => (
              <div key={i} className={styles.metaRow}>
                <input className="input" placeholder="Field name" value={m.key}
                  onChange={(e) => updateMeta(i, 'key', e.target.value)} style={{ maxWidth: 160 }} />
                <input className="input" placeholder="Value" value={m.value}
                  onChange={(e) => updateMeta(i, 'value', e.target.value)} />
                <button className={`btn btn-danger ${styles.metaRemoveBtn}`} onClick={() => removeMeta(i)}>×</button>
              </div>
            ))}
            <button className="btn btn-ghost" onClick={addMetaField}>+ Add field</button>
          </div>
        </details>

        <div className={styles.themeRow}>
          <label className="label">Appearance</label>
          <div className={styles.themeControls}>
            <div className={styles.themeItem}>
              <label className={`${styles.themeBtn} ${entryTheme.bg_color ? styles.themeBtnSet : ''}`}
                style={entryTheme.bg_color ? { background: entryTheme.bg_color } : {}}
                title={entryTheme.bg_color ? `Background: ${entryTheme.bg_color}` : 'Set background color'}>
                <input type="color" className={styles.hiddenColorInput}
                  value={entryTheme.bg_color ?? '#f5f5f5'}
                  onChange={(e) => setEntryTheme((prev) => ({ ...prev, bg_color: e.target.value }))} />
                {!entryTheme.bg_color && <span className={styles.themeBtnPlus}>+</span>}
              </label>
              {entryTheme.bg_color && (
                <button type="button" className={styles.themeClearBtn}
                  onClick={() => setEntryTheme((prev) => ({ ...prev, bg_color: null }))}
                  title="Remove background color">×</button>
              )}
              <span className={styles.themeItemLabel}>BG</span>
            </div>

            <div className={styles.themeItem}>
              <label className={`${styles.themeBtn} ${entryTheme.font_color ? styles.themeBtnSet : ''}`}
                style={entryTheme.font_color ? { background: entryTheme.font_color } : {}}
                title={entryTheme.font_color ? `Text: ${entryTheme.font_color}` : 'Set text color'}>
                <input type="color" className={styles.hiddenColorInput}
                  value={entryTheme.font_color ?? '#333333'}
                  onChange={(e) => setEntryTheme((prev) => ({ ...prev, font_color: e.target.value }))} />
                {!entryTheme.font_color && <span className={styles.themeBtnPlus}>+</span>}
              </label>
              {entryTheme.font_color && (
                <button type="button" className={styles.themeClearBtn}
                  onClick={() => setEntryTheme((prev) => ({ ...prev, font_color: null }))}
                  title="Remove text color">×</button>
              )}
              <span className={styles.themeItemLabel}>Text</span>
            </div>

            <div className={styles.themeItem}>
              <button type="button"
                className={`${styles.themeBtn} ${entryTheme.audio ? styles.themeBtnSet : ''}`}
                onClick={() => bgAudioInputRef.current?.click()}
                title={bgAudioMedia?.original_filename ?? (entryTheme.audio ? 'Background audio set' : 'Set background audio')}
                disabled={uploadingBgAudio}>
                <span className={styles.themeBtnPlus}>{uploadingBgAudio ? '…' : entryTheme.audio ? '♪' : '+'}</span>
              </button>
              {entryTheme.audio && (
                <button type="button" className={styles.themeClearBtn}
                  onClick={() => { setEntryTheme((prev) => ({ ...prev, audio: null })); setBgAudioMedia(null) }}
                  title="Remove background audio">×</button>
              )}
              <span className={styles.themeItemLabel}>Audio</span>
            </div>
          </div>
        </div>

        <details className={styles.metaPanel}>
          <summary className={styles.metaSummary}>Preferences</summary>
          <div className={styles.prefsFields}>
            <label className={styles.checkboxRow}>
              <input type="checkbox" checked={showAudioInline}
                onChange={(e) => setCustomMetadata((prev) => setShowAudioInlineFlag(prev, e.target.checked))} />
              <span>Show audio inline in entry reader</span>
            </label>
            <label className={styles.checkboxRow}>
              <input type="checkbox" checked={showUrlsInline}
                onChange={(e) => setCustomMetadata((prev) => setShowUrlsInlineFlag(prev, e.target.checked))} />
              <span>Show webpages inline in entry reader</span>
            </label>
            <label className={styles.checkboxRow}>
              <input type="checkbox" checked={identifyAudio}
                onChange={(e) => setCustomMetadata((prev) => setIdentifyAudioFlag(prev, e.target.checked))} />
              <span>Show rich metadata for audio</span>
            </label>
            <label className={styles.checkboxRow}>
              <input type="checkbox" checked={hideBgAudio}
                onChange={(e) => setCustomMetadata((prev) => setHideBgAudioFlag(prev, e.target.checked))} />
              <span>Hide background audio track from entry body</span>
            </label>
            <label className={styles.checkboxRow}>
              <input type="checkbox" checked={trackVersions}
                onChange={(e) => setCustomMetadata((prev) => setTrackVersionsFlag(prev, e.target.checked))} />
              <span>Track versions of this entry</span>
            </label>
            <label className={styles.checkboxRow}>
              <input type="checkbox" checked={useCustomDate}
                onChange={(e) => setUseCustomDate(e.target.checked)} />
              <span>Set custom creation date</span>
            </label>
            {useCustomDate && (
              <input type="datetime-local" className={`input ${styles.dateInput}`}
                value={customDate} onChange={(e) => setCustomDate(e.target.value)} />
            )}
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
                <input className={`input ${styles.webpageUrlInput}`}
                  placeholder="https://example.com/article"
                  value={webpageUrl} onChange={(e) => setWebpageUrl(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); void handleArchiveWebpage() } }} />
                <button className="btn" type="button"
                  disabled={archivingWebpage || !webpageUrl.trim()}
                  onClick={() => void handleArchiveWebpage()}>
                  {archivingWebpage ? 'Adding…' : 'Add Link'}
                </button>
              </div>
              <button className="btn btn-ghost" type="button" disabled={importingWebpage}
                onClick={() => webpageArchiveInputRef.current?.click()}>
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
                  Select text first to turn it into an internal entry link, or insert an entry title directly.
                  Results stay in the current journal when possible.
                </p>
              </div>
            </div>
            <div className={styles.linkSearchRow}>
              <input className={`input ${styles.linkSearchInput}`}
                placeholder="Search entries by name or text"
                value={linkQuery} onChange={(e) => setLinkQuery(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); void searchLinkableEntries(linkQuery) } }} />
              <button className="btn btn-ghost" type="button"
                onClick={() => void searchLinkableEntries(linkQuery)} disabled={linkingEntries}>
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
                      <span>{entry.tags[0]}</span>
                      <span>{new Date(entry.date_created).toLocaleDateString()}</span>
                    </p>
                  </div>
                  <button className="btn btn-ghost" type="button" onClick={() => insertEntryLink(entry)}>
                    Insert Link
                  </button>
                </article>
              ))}
            </div>
          </section>
        )}
      </div>

      <div className={`paper ${styles.editorWrap} ${stickyToolbar ? styles.editorWrapSticky : ''}`}>
        <div className={styles.toolbar}>
          <ToolbarBtn title="Bold" active={isActive.bold()} onClick={() => editor?.chain().focus().toggleBold().run()}>
            <strong>B</strong>
          </ToolbarBtn>
          <ToolbarBtn title="Italic" active={isActive.italic()} onClick={() => editor?.chain().focus().toggleItalic().run()}>
            <em>I</em>
          </ToolbarBtn>
          <ToolbarBtn title="Underline" active={isActive.underline()} onClick={() => editor?.chain().focus().toggleUnderline().run()}>
            <u>U</u>
          </ToolbarBtn>
          <ToolbarBtn title="Strikethrough" active={isActive.strike()} onClick={() => editor?.chain().focus().toggleStrike().run()}>
            <s>S</s>
          </ToolbarBtn>
          <span className={styles.toolbarSep} />
          <ToolbarBtn title="Heading 1" active={isActive.h1()} onClick={() => editor?.chain().focus().toggleHeading({ level: 1 }).run()}>H1</ToolbarBtn>
          <ToolbarBtn title="Heading 2" active={isActive.h2()} onClick={() => editor?.chain().focus().toggleHeading({ level: 2 }).run()}>H2</ToolbarBtn>
          <ToolbarBtn title="Heading 3" active={isActive.h3()} onClick={() => editor?.chain().focus().toggleHeading({ level: 3 }).run()}>H3</ToolbarBtn>
          <span className={styles.toolbarSep} />
          <ToolbarBtn title="Blockquote" active={isActive.blockquote()} onClick={() => editor?.chain().focus().toggleBlockquote().run()}>&ldquo;</ToolbarBtn>
          <ToolbarBtn title="Code block" active={isActive.codeBlock()} onClick={() => editor?.chain().focus().toggleCodeBlock().run()}>&lt;/&gt;</ToolbarBtn>
          <span className={styles.toolbarSep} />
          <ToolbarBtn title="Ordered list" active={isActive.orderedList()} onClick={() => editor?.chain().focus().toggleOrderedList().run()}>1.</ToolbarBtn>
          <ToolbarBtn title="Bullet list" active={isActive.bulletList()} onClick={() => editor?.chain().focus().toggleBulletList().run()}>•</ToolbarBtn>
          <span className={styles.toolbarSep} />
          <ToolbarBtn title="Insert link" active={isActive.link()}
            onClick={() => {
              const href = window.prompt('URL', editor?.getAttributes('link').href ?? '')
              if (href === null) return
              if (!href) { editor?.chain().focus().unsetLink().run(); return }
              editor?.chain().focus().setLink({ href }).run()
            }}>
            🔗
          </ToolbarBtn>
          <ToolbarBtn title="Insert media" onClick={() => mediaInputRef.current?.click()}>🖼︎</ToolbarBtn>
          <ToolbarBtn title="Insert webpage" onClick={() => setShowWebpagePanel((p) => !p)}>🌐︎</ToolbarBtn>
          <ToolbarBtn title="Link entry" onClick={toggleLinkPanel}>§</ToolbarBtn>
          <span className={styles.toolbarSep} />
          <ToolbarBtn title="Clear formatting" onClick={() => editor?.chain().focus().clearNodes().unsetAllMarks().run()}>✕</ToolbarBtn>
        </div>

        <EditorContent editor={editor} className={styles.editor} />
      </div>

      {error && <p className="error-text">{error}</p>}

      <div className={styles.actions}>
        <button className="btn btn-ghost" onClick={() => navigate(-1)}>← Back</button>
        <button className="btn" onClick={() => void save()} disabled={saving}>
          {saving ? 'Saving…' : 'Save Entry'}
        </button>
      </div>
    </div>
  )
}
