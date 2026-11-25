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
import { entryThemeStyle } from '../utils/entryTheme'
import { useWorkspaceStore } from '../stores/workspaceStore'
import { useEditorPrefsStore, CONTENT_WIDTH_MAP } from '../stores/editorPrefsStore'
import {
  listPendingWebpageMediaIds,
  mediaToWebpageEmbed,
} from '../utils/webpageEmbeds'
import { deltaToHtml } from '../utils/deltaToHtml'
import {
  hasTrackVersionsFlag,
  setTrackVersionsFlag,
} from '../utils/versionDiff'
import { AudioNode } from '../extensions/AudioNode'
import { PdfNode } from '../extensions/PdfNode'
import { VideoNode } from '../extensions/VideoNode'
import { WebpageNode } from '../extensions/WebpageNode'
import MusicTagPanel from '../components/MusicTagPanel'
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

interface ThemeColorButtonProps {
  label: string
  /** For tooltips / screen readers, e.g. "background color" */
  name: string
  value: string | null | undefined
  pickerDefault: string
  onChange: (value: string | null) => void
}

/** Round theme swatch: opens a color picker when empty; clicking a set color clears it. */
function ThemeColorButton({ label, name, value, pickerDefault, onChange }: ThemeColorButtonProps) {
  // The same <input type="color"> stays mounted in both states: the picker belongs to it,
  // and the first colour picked sets `value` - swapping elements then would close the
  // picker mid-pick. Once set, a click is intercepted to clear instead of reopening it.
  return (
    <div className={styles.themeItem}>
      <label className={`${styles.themeBtn} ${value ? styles.themeBtnSet : ''}`}
        style={value ? { background: value } : undefined}
        title={value
          ? `${name[0].toUpperCase()}${name.slice(1)}: ${value} (click to remove)`
          : `Set ${name}`}>
        <input type="color" className={styles.hiddenColorInput}
          aria-label={value ? `Remove ${name}` : `Set ${name}`}
          value={value ?? pickerDefault}
          onClick={(e) => {
            if (!value) return
            e.preventDefault() // don't open the picker
            onChange(null)
          }}
          onChange={(e) => onChange(e.target.value)} />
        {!value && <span className={styles.themeBtnPlus} aria-hidden="true" />}
      </label>
      <span className={styles.themeItemLabel}>{label}</span>
    </div>
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

  const [existingTags, setExistingTags] = useState<Tag[]>([])
  const [activeJournalId, setActiveJournalId] = useState(journalId)
  const [activeWorkspaceId, setActiveWorkspaceId] = useState(
    workspaceParam || locationWorkspaceId,
  )
  const [selectedTags, setSelectedTags] = useState<string[]>([])
  const [tagInput, setTagInput] = useState('')
  const [tagSuggestOpen, setTagSuggestOpen] = useState(false)
  const [activeTagSuggestion, setActiveTagSuggestion] = useState(-1)
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
  const [activeLinkResult, setActiveLinkResult] = useState(0)
  // Guards against out-of-order responses while searching as you type
  const linkSearchSeq = useRef(0)
  const [showWebpagePanel, setShowWebpagePanel] = useState(false)
  const [showMusicPanel, setShowMusicPanel] = useState(false)
  const [importingWebpage, setImportingWebpage] = useState(false)
  const [webpageUrl, setWebpageUrl] = useState('')
  const [archivingWebpage, setArchivingWebpage] = useState(false)
  const [pendingMusicLookup, setPendingMusicLookup] = useState(false)
  const [entryTheme, setEntryTheme] = useState<EntryTheme>({})
  const [bgAudioMedia, setBgAudioMedia] = useState<MediaRecord | null>(null)
  const [uploadingBgAudio, setUploadingBgAudio] = useState(false)
  const [initialContent, setInitialContent] = useState<string | null>(null)

  // Latest theme for callbacks that outlive a render (uploads, music downloads), so they
  // can tell whether the entry already has a background track.
  const entryThemeRef = useRef(entryTheme)
  useEffect(() => { entryThemeRef.current = entryTheme }, [entryTheme])

  // Make (or stop) an audio block already in the entry the background track. Uses only
  // state setters, which are stable, so the editor can hold onto it from the first render.
  const setBackgroundAudio = (mediaId: string, makeBackground: boolean) => {
    if (!makeBackground) {
      setEntryTheme((prev) => (prev.audio === mediaId ? { ...prev, audio: null } : prev))
      setBgAudioMedia((prev) => (prev?.id === mediaId ? null : prev))
      return
    }
    setEntryTheme((prev) => ({ ...prev, audio: mediaId }))
    mediaApi.getStatus(mediaId)
      .then((r) => {
        // Ignore if the background changed again while this was in flight
        if (entryThemeRef.current.audio === mediaId) setBgAudioMedia(r.data)
      })
      .catch(() => {})
  }

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
      AudioNode.configure({ onSetBackground: setBackgroundAudio }),
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

    // Re-attach placeholders for songs still downloading (or failed) from an earlier visit -
    // that state lives on the media record, not in the saved HTML.
    let cancelled = false
    for (const mediaId of extractAudioMediaIds(initialContent)) {
      mediaApi.getStatus(mediaId).then(({ data }) => {
        if (cancelled || data.status === 'completed') return
        editor.commands.updateAudioDownload(mediaId, {
          downloadStatus: data.status,
          downloadError: data.error_message,
        })
      }).catch(() => {})
    }
    return () => { cancelled = true }
  }, [initialContent, editor])

  // Songs being downloaded by the server - scanned from the live editor document
  const [pendingDownloadIds, setPendingDownloadIds] = useState<string[]>([])
  useEffect(() => {
    if (!editor) return
    const scan = () => {
      const ids: string[] = []
      editor.state.doc.descendants((node) => {
        if (node.type.name === 'audio' && node.attrs.downloadStatus === 'pending' && node.attrs.mediaId) {
          ids.push(node.attrs.mediaId as string)
        }
      })
      setPendingDownloadIds((prev) =>
        prev.length === ids.length && prev.every((id, i) => id === ids[i]) ? prev : ids)
    }
    scan()
    editor.on('update', scan)
    return () => { editor.off('update', scan) }
  }, [editor])

  // Keep each audio block's "Background" toggle in step with the entry's background track
  // (set from the toggle, the Theme controls, or on load).
  useEffect(() => {
    if (!editor) return
    const sync = () => { editor.commands.syncAudioBackground(entryTheme.audio ?? null) }
    sync()
    editor.on('update', sync)
    return () => { editor.off('update', sync) }
  }, [editor, entryTheme.audio, initialContent])

  // Poll pending song downloads, swapping each placeholder for its player when done
  useEffect(() => {
    if (pendingDownloadIds.length === 0 || !editor) return
    let cancelled = false
    const poll = async () => {
      for (const mediaId of pendingDownloadIds) {
        let media: MediaRecord
        try { media = (await mediaApi.getStatus(mediaId)).data } catch { continue }
        if (cancelled) return
        if (media.status === 'pending') continue
        editor.commands.updateAudioDownload(mediaId, {
          downloadStatus: media.status === 'failed' ? 'failed' : null,
          downloadError: media.error_message,
        })
        setBgAudioMedia((prev) => (prev?.id === media.id ? media : prev))
      }
    }
    const id = window.setInterval(() => { void poll() }, 2000)
    return () => { cancelled = true; window.clearInterval(id) }
  }, [pendingDownloadIds, editor])

  useEffect(() => {
    if (!activeWorkspaceId) { setExistingTags([]); return }
    let active = true
    tagsApi.list()
      .then((r) => { if (active) setExistingTags([...r.data].sort((a, b) => a.name.localeCompare(b.name))) })
      .catch(() => { if (active) setExistingTags([]) })
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
          // New audio becomes the background only if the entry doesn't have one yet;
          // otherwise use "Set as background" on the block.
          if (!entryThemeRef.current.audio) {
            setEntryTheme((prev) => ({ ...prev, audio: res.data.id }))
            setBgAudioMedia(res.data)
          }
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
      setShowWebpagePanel(false)
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
      setShowWebpagePanel(false)
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, 'Failed to queue webpage archive.'))
    } finally {
      setArchivingWebpage(false)
    }
  }

  // ── Link panel ────────────────────────────────────────────────────────────────

  // Searches the current journal first, falling back to all of the user's entries.
  const searchLinkableEntries = async (query: string) => {
    const seq = ++linkSearchSeq.current
    const isCurrent = () => seq === linkSearchSeq.current
    setLinkSearchError('')
    setLinkingEntries(true)
    try {
      const params = { q: query.trim() || undefined, limit: 8, offset: 0 }
      let results: Entry[] = []
      let scope: 'journal' | 'global' = 'global'
      if (activeJournalId) {
        const res = await entriesApi.search({ ...params, journal_id: activeJournalId })
        results = res.data.filter((e) => e.id !== entryId)
        if (results.length > 0) scope = 'journal'
      }
      if (results.length === 0) {
        const res = await entriesApi.search(params)
        results = res.data.filter((e) => e.id !== entryId)
      }
      if (!isCurrent()) return
      setLinkResults(results)
      setLinkResultsScope(scope)
      setActiveLinkResult(0)
    } catch (err: unknown) {
      if (!isCurrent()) return
      setLinkSearchError(getApiErrorMessage(err, 'Failed to search entries.'))
      setLinkResults([]); setLinkResultsScope(null)
    } finally {
      if (isCurrent()) setLinkingEntries(false)
    }
  }

  // Search as you type (debounced) while the link panel is open
  useEffect(() => {
    if (!showLinkPanel) return
    const id = window.setTimeout(() => { void searchLinkableEntries(linkQuery) }, 250)
    return () => window.clearTimeout(id)
  }, [showLinkPanel, linkQuery]) // eslint-disable-line react-hooks/exhaustive-deps

  // A song the server is now fetching (music panel): insert it like an audio upload right
  // away - its URL is final - showing a placeholder card until the download finishes.
  const handleMusicQueued = (media: MediaRecord, label: string) => {
    if (!editor) return
    editor.chain().focus().insertAudio({
      src: media.resource_path,
      originalFilename: media.original_filename,
      mediaId: media.id,
      downloadStatus: media.status === 'pending' ? 'pending' : null,
      downloadLabel: label,
    }).run()
    if (!entryThemeRef.current.audio) {
      setEntryTheme((prev) => ({ ...prev, audio: media.id }))
      setBgAudioMedia(media)
    }
    setCustomMetadata((prev) => setIdentifyAudioFlag(prev, true))
    setShowMusicPanel(false)
  }

  const toggleLinkPanel = () => setShowLinkPanel((prev) => !prev)

  const handleLinkSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (!linkResults.length) return
      e.preventDefault()
      const step = e.key === 'ArrowDown' ? 1 : -1
      setActiveLinkResult((i) => (i + step + linkResults.length) % linkResults.length)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      const entry = linkResults[activeLinkResult]
      if (entry) insertEntryLink(entry)
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setShowLinkPanel(false)
      editor?.commands.focus()
    }
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

  // ── Tag helpers ───────────────────────────────────────────────────────────────

  const addTag = (raw: string) => {
    const trimmed = raw.trim()
    if (!trimmed) return
    setSelectedTags((prev) => prev.includes(trimmed) ? prev : [...prev, trimmed])
    setTagInput('')
  }
  const removeTag = (tag: string) => setSelectedTags((prev) => prev.filter((t) => t !== tag))

  // Existing tags matching what's typed - prefix matches first. (A themed stand-in for
  // <datalist>, whose popup the browser draws in fixed white.)
  const tagSuggestions = useMemo(() => {
    const q = tagInput.trim().toLowerCase()
    const available = existingTags.map((t) => t.name).filter((n) => !selectedTags.includes(n))
    const matches = q ? available.filter((n) => n.toLowerCase().includes(q)) : available
    return matches
      .sort((a, b) => Number(!a.toLowerCase().startsWith(q)) - Number(!b.toLowerCase().startsWith(q)))
      .slice(0, 8)
  }, [existingTags, selectedTags, tagInput])
  const showTagSuggestions = tagSuggestOpen && tagSuggestions.length > 0

  const pickTag = (name: string) => {
    addTag(name)
    setActiveTagSuggestion(-1)
  }

  const handleTagKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (!tagSuggestions.length) return
      e.preventDefault()
      setTagSuggestOpen(true)
      // Cycle through -1 (nothing highlighted), 0 … n-1
      const step = e.key === 'ArrowDown' ? 1 : -1
      const slots = tagSuggestions.length + 1
      setActiveTagSuggestion((i) => ((i + 1 + step + slots) % slots) - 1)
    } else if (e.key === 'Escape') {
      if (showTagSuggestions) { e.preventDefault(); setTagSuggestOpen(false); setActiveTagSuggestion(-1) }
    } else if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      const highlighted = showTagSuggestions ? tagSuggestions[activeTagSuggestion] : undefined
      if (highlighted) pickTag(highlighted)
      else addTag(tagInput)
    } else if (e.key === 'Backspace' && !tagInput && selectedTags.length > 0) {
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
        if (!existingTags.find((t) => t.name === tag)) {
          try {
            const created = await tagsApi.create(tag)
            setExistingTags((prev) => [...prev, created.data].sort((a, b) => a.name.localeCompare(b.name)))
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
  }), [editor])

  // Live preview of the entry theme, applied the same way the reader does: background on
  // the paper (replacing its texture), text colour on the body text.
  const editorThemeStyle = entryThemeStyle(entryTheme)

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
                role="combobox"
                aria-autocomplete="list"
                aria-expanded={showTagSuggestions}
                aria-controls="tag-suggestions"
                aria-activedescendant={showTagSuggestions && activeTagSuggestion >= 0
                  ? `tag-suggestion-${activeTagSuggestion}` : undefined}
                placeholder={selectedTags.length === 0 ? 'e.g. Reflection, Dream…' : 'Add tag…'}
                value={tagInput}
                onChange={(e) => { setTagInput(e.target.value); setTagSuggestOpen(true); setActiveTagSuggestion(-1) }}
                onFocus={() => setTagSuggestOpen(true)}
                onKeyDown={handleTagKeyDown}
                onBlur={() => {
                  setTagSuggestOpen(false)
                  setActiveTagSuggestion(-1)
                  if (tagInput.trim()) addTag(tagInput)
                }} />
            </div>
            {showTagSuggestions && (
              <ul id="tag-suggestions" role="listbox" className={styles.tagSuggestions}>
                {tagSuggestions.map((name, i) => (
                  <li key={name} id={`tag-suggestion-${i}`} role="option"
                    aria-selected={i === activeTagSuggestion}
                    className={`${styles.tagSuggestion} ${i === activeTagSuggestion ? styles.tagSuggestionActive : ''}`}
                    // mousedown, not click: keep focus in the input so blur doesn't commit the typed text first
                    onMouseDown={(e) => { e.preventDefault(); pickTag(name) }}
                    onMouseEnter={() => setActiveTagSuggestion(i)}>
                    {name}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className={styles.themeRow}>
          <label className="label">Theme</label>
          <div className={styles.themeControls}>
            <ThemeColorButton label="BG" name="background color" value={entryTheme.bg_color}
              pickerDefault="#f5f5f5"
              onChange={(bg_color) => setEntryTheme((prev) => ({ ...prev, bg_color }))} />
            <ThemeColorButton label="Text" name="text color" value={entryTheme.font_color}
              pickerDefault="#333333"
              onChange={(font_color) => setEntryTheme((prev) => ({ ...prev, font_color }))} />

            <div className={styles.themeItem}>
              <button type="button"
                className={`${styles.themeBtn} ${entryTheme.audio ? styles.themeBtnSet : ''}`}
                onClick={() => {
                  if (entryTheme.audio) {
                    setEntryTheme((prev) => ({ ...prev, audio: null }))
                    setBgAudioMedia(null)
                  } else {
                    bgAudioInputRef.current?.click()
                  }
                }}
                title={entryTheme.audio
                  ? `Background audio: ${bgAudioMedia?.original_filename ?? 'set'} (click to remove)`
                  : 'Set background audio'}
                aria-label={entryTheme.audio ? 'Remove background audio' : 'Set background audio'}
                disabled={uploadingBgAudio}>
                {uploadingBgAudio
                  ? <span className={styles.themeBtnGlyph}>…</span>
                  : entryTheme.audio
                    ? <span className={styles.themeBtnGlyph}>♪</span>
                    : <span className={styles.themeBtnPlus} aria-hidden="true" />}
              </button>
              <span className={styles.themeItemLabel}>Audio</span>
            </div>
          </div>
        </div>

        <details className={styles.metaPanel}>
          <summary className={styles.metaSummary}>Preferences</summary>
          <div className={styles.prefsFields}>
            <fieldset className={styles.prefsSection}>
              <legend className={styles.prefsLegend}>Audio</legend>
              <label className={styles.checkboxRow}>
                <input type="checkbox" checked={showAudioInline}
                  onChange={(e) => setCustomMetadata((prev) => setShowAudioInlineFlag(prev, e.target.checked))} />
                <span>Show audio inline in entry reader</span>
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
            </fieldset>

            <fieldset className={styles.prefsSection}>
              <legend className={styles.prefsLegend}>Webpages</legend>
              <label className={styles.checkboxRow}>
                <input type="checkbox" checked={showUrlsInline}
                  onChange={(e) => setCustomMetadata((prev) => setShowUrlsInlineFlag(prev, e.target.checked))} />
                <span>Show webpages inline in entry reader</span>
              </label>
            </fieldset>

            <fieldset className={styles.prefsSection}>
              <legend className={styles.prefsLegend}>Entry</legend>
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
            </fieldset>
          </div>
        </details>

      </div>

      <div className={`paper ${styles.editorWrap} ${stickyToolbar ? styles.editorWrapSticky : ''}`}
        style={editorThemeStyle}>
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
          <ToolbarBtn title="Insert media" onClick={() => mediaInputRef.current?.click()}>🖼︎</ToolbarBtn>
          <ToolbarBtn title="Insert webpage" active={showWebpagePanel} onClick={() => setShowWebpagePanel((p) => !p)}>🌐︎</ToolbarBtn>
          <ToolbarBtn title="Tag a song" active={showMusicPanel} onClick={() => setShowMusicPanel((p) => !p)}>♫</ToolbarBtn>
          <ToolbarBtn title="Link entry" active={showLinkPanel} onClick={toggleLinkPanel}>§</ToolbarBtn>
          <span className={styles.toolbarSep} />
          <ToolbarBtn title="Clear formatting" onClick={() => editor?.chain().focus().clearNodes().unsetAllMarks().run()}>✕</ToolbarBtn>
        </div>

        {showWebpagePanel && (
          <div className={styles.webpageBar} role="group" aria-label="Insert webpage">
            <input className={styles.webpageUrlInput} autoFocus
              type="url" placeholder="Paste a URL to archive…" aria-label="Webpage URL to archive"
              value={webpageUrl} onChange={(e) => setWebpageUrl(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') { e.preventDefault(); void handleArchiveWebpage() }
                else if (e.key === 'Escape') { e.preventDefault(); setShowWebpagePanel(false); editor?.commands.focus() }
              }} />
            <button className="btn" type="button"
              disabled={archivingWebpage || !webpageUrl.trim()}
              onClick={() => void handleArchiveWebpage()}>
              {archivingWebpage ? 'Adding…' : 'Archive'}
            </button>
            <button className="btn btn-ghost" type="button" disabled={importingWebpage}
              title="Import a page saved with the SingleFile browser extension"
              onClick={() => webpageArchiveInputRef.current?.click()}>
              {importingWebpage ? 'Importing…' : 'Import HTML'}
            </button>
          </div>
        )}

        {showMusicPanel && entryId && (
          <MusicTagPanel entryId={entryId} onQueued={handleMusicQueued}
            onClose={() => { setShowMusicPanel(false); editor?.commands.focus() }} />
        )}

        {showLinkPanel && (
          <section className={styles.linkBar} aria-label="Link another entry">
            <div className={styles.linkSearchRow}>
                            <input className={styles.linkSearchInput} autoFocus
                placeholder="Search entries to link…"
                aria-label="Search entries to link"
                role="combobox"
                aria-expanded={linkResults.length > 0}
                aria-controls="link-entry-results"
                aria-activedescendant={linkResults.length ? `link-entry-${activeLinkResult}` : undefined}
                value={linkQuery} onChange={(e) => setLinkQuery(e.target.value)}
                onKeyDown={handleLinkSearchKeyDown} />
              {linkingEntries && <span className={styles.linkStatus}>…</span>}
            </div>
            {linkSearchError && <p className={`error-text ${styles.linkStatus}`}>{linkSearchError}</p>}
            {!linkingEntries && !linkSearchError && linkResults.length === 0 && linkResultsScope && (
              <p className={styles.linkStatus}>No matching entries</p>
            )}
            {linkResults.length > 0 && (
              <>
                {linkResultsScope === 'global' && activeJournalId && (
                  <p className={styles.linkStatus}>From other journals</p>
                )}
                <ul id="link-entry-results" role="listbox" className={styles.linkResults}>
                  {linkResults.map((entry, i) => (
                    <li key={entry.id} id={`link-entry-${i}`} role="option"
                      aria-selected={i === activeLinkResult}
                      className={`${styles.linkResult} ${i === activeLinkResult ? styles.linkResultActive : ''}`}
                      // mousedown: keep the editor selection that the link will wrap
                      onMouseDown={(e) => { e.preventDefault(); insertEntryLink(entry) }}
                      onMouseEnter={() => setActiveLinkResult(i)}>
                      <span className={styles.linkResultTitle}>{formatEntryLinkLabel(entry)}</span>
                      <span className={styles.linkResultDate}>
                        {new Date(entry.date_created).toLocaleDateString()}
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </section>
        )}

        <input className={styles.nameInput} placeholder="Name" aria-label="Entry name"
          title="Leave empty to name the entry after its date"
          value={entryName} onChange={(e) => setEntryName(e.target.value)}
          onKeyDown={(e) => {
            // Enter moves on to the body, like leaving a document title
            if (e.key === 'Enter') { e.preventDefault(); editor?.commands.focus('start') }
          }} />
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
