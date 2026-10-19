import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import ImageExt from '@tiptap/extension-image'
import LinkExt from '@tiptap/extension-link'
import Underline from '@tiptap/extension-underline'
import { entriesApi, mediaApi, type Entry, type EntryVersion, type MediaRecord, type MusicInfo, workspacesApi, journalsApi } from '../services/api'
import { useAuthStore } from '../stores/authStore'
import { useWorkspaceStore } from '../stores/workspaceStore'
import { useEditorPrefsStore, CONTENT_WIDTH_MAP } from '../stores/editorPrefsStore'
import {
  extractWebpageEmbeds,
  getWebpageSourceLabel,
  listPendingWebpageMediaIds,
  syncWebpageEmbedsWithMedia,
  type WebpageEmbedValue,
} from '../utils/webpageEmbeds'
import { deltaToHtml } from '../utils/deltaToHtml'
import {
  TRACK_VERSIONS_KEY,
  computeWordDiff,
  extractTextFromHtml,
} from '../utils/versionDiff'
import { AudioNode } from '../extensions/AudioNode'
import { PdfNode } from '../extensions/PdfNode'
import { VideoNode } from '../extensions/VideoNode'
import { WebpageNode } from '../extensions/WebpageNode'
import { getApiErrorMessage } from '../utils/errors'
import { fmtDate } from '../utils/datetime'
import styles from './EntryReader.module.css'

const AUDIO_EXTENSIONS = new Set([
  '.mp3', '.aac', '.flac', '.wav', '.m4a', '.ogg', '.oga', '.alac', '.opus',
])

function isAudioUrl(raw: string): boolean {
  if (!raw) return false
  try {
    const url = new URL(raw, window.location.origin)
    return Array.from(AUDIO_EXTENSIONS).some((ext) => url.pathname.toLowerCase().endsWith(ext))
  } catch {
    return false
  }
}

interface AudioSource {
  src: string
  originalFilename?: string
  mediaId?: string
}

const SHOW_AUDIO_INLINE_KEY = 'show-audio-inline'
const SHOW_URLS_INLINE_KEY = 'show-urls-inline'
const IDENTIFY_AUDIO_KEY = 'identify-audio'
const HIDE_BG_AUDIO_KEY = 'hide-bg-audio'

function metaFlag(metadata: Entry['custom_metadata'], key: string): boolean {
  const match = metadata.find((f) => f.key === key)
  if (!match) return false
  return ['true', '1', 'yes', 'on'].includes(match.value.trim().toLowerCase())
}

function extractAudioSources(body: string): AudioSource[] {
  if (typeof body !== 'string') return []
  const doc = new DOMParser().parseFromString(body, 'text/html')
  const sources = new Map<string, AudioSource>()
  for (const el of doc.querySelectorAll('audio[src]')) {
    const src = el.getAttribute('src') ?? ''
    if (!src || !isAudioUrl(src)) continue
    const originalFilename = el.getAttribute('data-original-filename') || undefined
    const mediaId = el.getAttribute('data-media-id') || undefined
    if (!sources.has(src)) sources.set(src, { src, originalFilename, mediaId })
  }
  return Array.from(sources.values())
}

function filterBgAudioFromHtml(html: string, bgAudioMediaId: string): string {
  if (!html) return html
  const doc = new DOMParser().parseFromString(html, 'text/html')
  for (const el of doc.querySelectorAll(`audio[data-media-id="${CSS.escape(bgAudioMediaId)}"]`)) {
    el.remove()
  }
  return doc.body.innerHTML
}

function removeWebpageEmbedsFromHtml(html: string): string {
  if (!html) return html
  const doc = new DOMParser().parseFromString(html, 'text/html')
  for (const el of doc.querySelectorAll('div[data-type="webpage"]')) {
    el.remove()
  }
  return doc.body.innerHTML
}

function hasLiveSourceUrl(sourceUrl: string): boolean {
  return /^https?:\/\//i.test(sourceUrl.trim())
}

function getFileExtension(raw: string): string {
  try {
    const url = new URL(raw, window.location.origin)
    const lastDot = url.pathname.lastIndexOf('.')
    if (lastDot === -1) return 'AUDIO'
    return url.pathname.slice(lastDot + 1).toUpperCase() || 'AUDIO'
  } catch {
    return 'AUDIO'
  }
}

function getFileName(raw: string): string {
  try {
    const url = new URL(raw, window.location.origin)
    return decodeURIComponent(url.pathname.split('/').filter(Boolean).pop() ?? raw)
  } catch {
    return raw
  }
}

function formatDuration(seconds?: number): string {
  if (!seconds || Number.isNaN(seconds) || !Number.isFinite(seconds)) return '--:--'
  const total = Math.max(0, Math.round(seconds))
  return `${Math.floor(total / 60)}:${(total % 60).toString().padStart(2, '0')}`
}

function getDisplayName(source: AudioSource): string {
  return source.originalFilename?.trim() || getFileName(source.src)
}

export default function EntryReader() {
  const { entryId } = useParams<{ entryId: string }>()
  const location = useLocation()
  const navigate = useNavigate()
  const isPrivilegedMode = useAuthStore((s) => s.isPrivilegedMode)

  const [entry, setEntry] = useState<Entry | null>(null)
  const [loading, setLoading] = useState(true)
  const [audioMediaInfo, setAudioMediaInfo] = useState<Record<string, MediaRecord>>({})
  const [durations, setDurations] = useState<Record<string, number>>({})
  const [displayHtml, setDisplayHtml] = useState<string>('')

  const bgAudioRef = useRef<HTMLAudioElement | null>(null)
  const [bgAudioMedia, setBgAudioMedia] = useState<MediaRecord | null>(null)

  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const [showMovePanel, setShowMovePanel] = useState(false)
  const [moveWorkspaces, setMoveWorkspaces] = useState<Array<{ id: string; name: string }>>([])
  const [moveTargetWorkspaceId, setMoveTargetWorkspaceId] = useState('')
  const [moveJournals, setMoveJournals] = useState<Array<{ id: string; name: string }>>([])
  const [moveTargetJournalId, setMoveTargetJournalId] = useState('')
  const [moving, setMoving] = useState(false)
  const [moveError, setMoveError] = useState('')
  const [versions, setVersions] = useState<EntryVersion[]>([])
  const [expandedVersionId, setExpandedVersionId] = useState<string | null>(null)
  const [showVersionSidebar, setShowVersionSidebar] = useState(false)
  const activeJournal = useWorkspaceStore((s) => s.activeJournal)
  const journals = useWorkspaceStore((s) => s.journals)
  const { contentWidth } = useEditorPrefsStore()

  const editor = useEditor({
    extensions: [
      StarterKit,
      ImageExt,
      LinkExt.configure({ openOnClick: false }),
      Underline,
      AudioNode,
      PdfNode,
      VideoNode,
      WebpageNode,
    ],
    content: '',
    editable: false,
  })

  // Load entry
  useEffect(() => {
    if (!entryId) return
    entriesApi.get(entryId)
      .then((r) => {
        setEntry(r.data)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [entryId])

  // Load version history when entry has track-versions enabled
  useEffect(() => {
    if (!entry) return
    if (!metaFlag(entry.custom_metadata, TRACK_VERSIONS_KEY)) {
      setVersions([])
      return
    }
    entriesApi.listVersions(entry.id)
      .then((r) => setVersions(r.data))
      .catch(() => { })
  }, [entry])

  // When entry loads, normalize body and compute displayHtml
  useEffect(() => {
    if (!entry || !editor) return
    const rawBody = entry.body as unknown
    const html = typeof rawBody === 'string' ? rawBody : deltaToHtml(rawBody)

    const hideBgAudio = metaFlag(entry.custom_metadata, HIDE_BG_AUDIO_KEY)
    const showUrlsInline = metaFlag(entry.custom_metadata, SHOW_URLS_INLINE_KEY)
    const bgAudioMediaId = entry.theme?.audio ?? null

    let processed = html
    if (!showUrlsInline) processed = removeWebpageEmbedsFromHtml(processed)
    if (hideBgAudio && bgAudioMediaId) processed = filterBgAudioFromHtml(processed, bgAudioMediaId)

    setDisplayHtml(processed)
    editor.commands.setContent(processed)
  }, [entry, editor])

  // Update displayHtml when editor content changes (from polling updates)
  useEffect(() => {
    if (!editor) return
    const handler = () => {
      setDisplayHtml(editor.getHTML())
    }
    editor.on('update', handler)
    return () => { editor.off('update', handler) }
  }, [editor])

  // Poll pending webpage archives
  useEffect(() => {
    if (!entry) return
    const pendingIds = listPendingWebpageMediaIds(entry.body as unknown)
    if (pendingIds.length === 0) return
    let cancelled = false

    const poll = async () => {
      const responses = await Promise.all(
        pendingIds.map(async (id) => {
          try { return (await mediaApi.getStatus(id)).data } catch { return null }
        }),
      )
      if (cancelled) return
      const mediaById = new Map<string, MediaRecord>()
      for (const m of responses) { if (m) mediaById.set(m.id, m) }
      if (!mediaById.size) return

      setEntry((cur) => {
        if (!cur) return cur
        const nextBody = syncWebpageEmbedsWithMedia(cur.body, mediaById)
        if (nextBody === cur.body) return cur
        return { ...cur, body: nextBody as string }
      })
    }

    void poll()
    const id = window.setInterval(() => { void poll() }, 2000)
    return () => { cancelled = true; window.clearInterval(id) }
  }, [entry])

  // Fetch music metadata for audio sources
  useEffect(() => {
    if (!entry) return
    const sources = extractAudioSources(displayHtml)
    if (sources.length === 0) return
    let cancelled = false
    const fetch = async () => {
      for (const source of sources) {
        if (cancelled) break
        if (audioMediaInfo[source.src] || !source.mediaId) continue
        try {
          const res = await mediaApi.getStatus(source.mediaId)
          if (!cancelled) setAudioMediaInfo((prev) => ({ ...prev, [source.src]: res.data }))
        } catch { }
      }
    }
    void fetch()
    return () => { cancelled = true }
  }, [entry, displayHtml])

  // Poll for pending music lookups
  useEffect(() => {
    const pending = Object.entries(audioMediaInfo)
      .filter(([, m]) => (m.custom_metadata as Record<string, unknown> | null)?.music_lookup_status === 'pending')
      .map(([src, m]) => ({ src, mediaId: m.id }))
    if (pending.length === 0) return
    let cancelled = false
    const poll = async () => {
      for (const { src, mediaId } of pending) {
        if (cancelled) break
        try {
          const res = await mediaApi.getStatus(mediaId)
          if (!cancelled) setAudioMediaInfo((prev) => ({ ...prev, [src]: res.data }))
        } catch { }
      }
    }
    const id = window.setInterval(() => { void poll() }, 3000)
    return () => { cancelled = true; window.clearInterval(id) }
  }, [audioMediaInfo])

  // Fetch bg audio media
  useEffect(() => {
    if (!entry?.theme?.audio) return
    let cancelled = false
    mediaApi.getStatus(entry.theme.audio)
      .then((r) => { if (!cancelled) setBgAudioMedia(r.data) })
      .catch(() => { })
    return () => { cancelled = true }
  }, [entry?.theme?.audio])

  // Autoplay bg audio (only when hide-bg-audio is set)
  useEffect(() => {
    if (!bgAudioMedia || !entry) return
    if (!metaFlag(entry.custom_metadata, HIDE_BG_AUDIO_KEY)) return
    bgAudioRef.current?.play().catch(() => { })
  }, [bgAudioMedia]) // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return <div className={styles.loading}>Loading…</div>
  if (!entry) return <div className={styles.loading}>Entry not found.</div>

  const hideBgAudio = metaFlag(entry.custom_metadata, HIDE_BG_AUDIO_KEY)
  const bgAudioMediaId = entry.theme?.audio ?? null
  const showAudioInline = metaFlag(entry.custom_metadata, SHOW_AUDIO_INLINE_KEY)
  const showRichAudio = metaFlag(entry.custom_metadata, IDENTIFY_AUDIO_KEY)
  const showUrlsInline = metaFlag(entry.custom_metadata, SHOW_URLS_INLINE_KEY)
  const trackVersions = metaFlag(entry.custom_metadata, TRACK_VERSIONS_KEY)

  const allAudioSources = extractAudioSources(displayHtml)
  const audioSources = (hideBgAudio && bgAudioMediaId)
    ? allAudioSources.filter((s) => s.mediaId !== bgAudioMediaId)
    : allAudioSources
  const webpageSources = extractWebpageEmbeds(entry.body as unknown)

  const getMusicInfo = (src: string): MusicInfo | null => {
    const media = audioMediaInfo[src]
    if (!media?.custom_metadata) return null
    const info = (media.custom_metadata as Record<string, unknown>).music_info
    if (!info || typeof info !== 'object') return null
    return info as MusicInfo
  }

  const entryTitle = entry.name?.trim() || fmtDate(entry.date_created, entry.timezone)
  const locationWorkspaceId = ((location.state as { workspaceId?: string } | null)?.workspaceId ?? '')
  const entryWorkspaceId =
    locationWorkspaceId
    || (activeJournal?.id === entry.journal_id ? activeJournal.workspace_id : '')
    || journals.find((j) => j.id === entry.journal_id)?.workspace_id
    || ''

  const bgColor = entry.theme?.bg_color || undefined
  const fontColor = entry.theme?.font_color || undefined
  const bgAudioSrc = bgAudioMedia?.resource_path
  const bgCoverArt = bgAudioMedia
    ? ((bgAudioMedia.custom_metadata as Record<string, unknown> | null)
      ?.music_info as MusicInfo | null)?.cover_art_base64
    : undefined
  const hasGlassEffect = !!bgCoverArt
  const articleStyle = {
    ...(bgColor ? { backgroundColor: bgColor, backgroundImage: 'none' } : {}),
    ...(fontColor ? { '--entry-font-color': fontColor } : {}),
  } as React.CSSProperties

  const handleBodyClick = (event: React.MouseEvent<HTMLDivElement>) => {
    if (event.defaultPrevented || event.button !== 0) return
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    if (!(event.target instanceof Element)) return
    const anchor = event.target.closest('a')
    if (!(anchor instanceof HTMLAnchorElement)) return
    const href = anchor.getAttribute('href')
    if (!href) return
    let url: URL
    try { url = new URL(href, window.location.href) } catch { return }
    if (url.origin !== window.location.origin) return
    if (!/^\/entries\/[^/]+\/?$/.test(url.pathname)) return
    event.preventDefault()
    navigate(`${url.pathname}${url.search}${url.hash}`)
  }

  const handleDelete = async () => {
    setDeleteError('')
    setDeleting(true)
    try {
      await entriesApi.remove(entry.id)
      window.dispatchEvent(new Event('codexj-bin-changed'))
      navigate(`/journals/${entry.journal_id}/`)
    } catch (err: unknown) {
      setDeleteError(getApiErrorMessage(err, 'Could not move entry to Bin.'))
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className={`${styles.pageOuter}${showVersionSidebar ? ` ${styles.pageOuterShifted}` : ''}`}>
      <div className={styles.page} style={{ maxWidth: CONTENT_WIDTH_MAP[contentWidth] }}>
        {hasGlassEffect && bgCoverArt && (
          <div
            className={styles.pageBgGlass}
            style={{ backgroundImage: `url(data:image/jpeg;base64,${bgCoverArt})` }}
          />
        )}
        <div className={`paper ${styles.article}${(hasGlassEffect && !bgColor) ? ` ${styles.articleGlassMode}` : ''}`}
          style={Object.keys(articleStyle).length ? articleStyle : undefined}>
          <div className={styles.titleRow}>
            <h1 className={styles.entryTitle}>{entryTitle}</h1>
            {trackVersions && (
              <button
                className={`${styles.vcBtn}${showVersionSidebar ? ` ${styles.vcBtnActive}` : ''}`}
                title="Version History"
                onClick={() => setShowVersionSidebar((v) => !v)}
              >
                <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  {/* Clockwise arc ~330°, gap at top between 12 and 1 o'clock */}
                  <path d="M10.75 3.24A5.5 5.5 0 1 1 8 2.5" />
                  {/* Arrowhead at 12 o'clock pointing right (clockwise direction) */}
                  <polyline points="6.5 1.5 8 2.5 6.5 3.5" />
                  {/* Clock hands: up toward 12, down-left toward ~8 */}
                  <line x1="8" y1="8" x2="8" y2="5.5" />
                  <line x1="8" y1="8" x2="6" y2="10.5" />
                </svg>
              </button>
            )}
          </div>
          <div className={styles.meta}>
            <span className={styles.date}>{fmtDate(entry.date_created, entry.timezone)}</span>
            <span className={styles.tagsRow}>
              {entry.tags.map((tag) => (
                <span key={tag} className={styles.tag}>{tag}</span>
              ))}
            </span>
          </div>

          <div
            className={showAudioInline ? styles.body : `${styles.body} ${styles.hideInlineAudio}`}
            onClick={handleBodyClick}
          >
            <EditorContent editor={editor} />
          </div>

          {!showAudioInline && audioSources.length > 0 && (
            <section className={styles.audioSection}>
              <h3>Audio</h3>
              <div className={styles.audioList}>
                {audioSources.map((source) => {
                  const musicInfo = getMusicInfo(source.src)
                  if (showRichAudio && musicInfo && musicInfo.title) {
                    return (
                      <article key={source.src} className={`${styles.audioCard} ${styles.musicCard}`}>
                        <div className={styles.musicCardInner}>
                          {musicInfo.cover_art_base64 && (
                            <img
                              src={`data:image/jpeg;base64,${musicInfo.cover_art_base64}`}
                              alt={`${musicInfo.album || musicInfo.title} cover`}
                              className={styles.coverArt}
                            />
                          )}
                          <div className={styles.musicMeta}>
                            <p className={styles.musicTitle}>{musicInfo.title}</p>
                            {musicInfo.artist && <p className={styles.musicArtist}>{musicInfo.artist}</p>}
                            <div className={styles.musicDetails}>
                              {musicInfo.album && <span className={styles.musicAlbum}>{musicInfo.album}</span>}
                              {musicInfo.year && <span className={styles.musicYear}>{musicInfo.year}</span>}
                            </div>
                          </div>
                        </div>
                        <audio controls preload="metadata" src={source.src} className={styles.audioPlayer}
                          onLoadedMetadata={(e) => {
                            const d = e.currentTarget.duration
                            if (d && !Number.isNaN(d) && Number.isFinite(d))
                              setDurations((prev) => ({ ...prev, [source.src]: d }))
                          }}>
                          Your browser does not support the audio element.
                        </audio>
                      </article>
                    )
                  }
                  return (
                    <article key={source.src} className={styles.audioCard}>
                      <div className={styles.audioMetaRow}>
                        <span className={styles.fileTypeBadge}>{getFileExtension(source.src)}</span>
                        <span className={styles.durationBadge}>{formatDuration(durations[source.src])}</span>
                      </div>
                      <p className={styles.audioName}>{getDisplayName(source)}</p>
                      <audio controls preload="metadata" src={source.src} className={styles.audioPlayer}
                        onLoadedMetadata={(e) => {
                          const d = e.currentTarget.duration
                          if (d && !Number.isNaN(d) && Number.isFinite(d))
                            setDurations((prev) => ({ ...prev, [source.src]: d }))
                        }}>
                        Your browser does not support the audio element.
                      </audio>
                    </article>
                  )
                })}
              </div>
            </section>
          )}

          {!showUrlsInline && webpageSources.length > 0 && (
            <section className={styles.webpageSection}>
              <h3>Webpages</h3>
              <div className={styles.webpageList}>
                {webpageSources.map((page: WebpageEmbedValue) => (
                  <article key={page.src || page.source_url} className={styles.webpageCard}>
                    <div className={styles.webpageIcon}>🌐︎</div>
                    <div className={styles.webpageInfo}>
                      <p className={styles.webpageTitle}>
                        {page.status === 'pending'
                          ? 'Archiving webpage…'
                          : page.title || getWebpageSourceLabel(page.source_url)}
                      </p>
                      <p className={styles.webpageUrl}>{getWebpageSourceLabel(page.source_url)}</p>
                      {page.status === 'pending' && <p className={styles.webpageStatus}>Archiving in background</p>}
                      {page.status === 'failed' && (
                        <p className={`${styles.webpageStatus} ${styles.webpageStatusError}`}>
                          {page.error_message || 'Archive failed'}
                        </p>
                      )}
                    </div>
                    <div className={styles.webpageActions}>
                      {hasLiveSourceUrl(page.source_url) && (
                        <a href={page.source_url} target="_blank" rel="noopener noreferrer"
                          className={styles.webpageLinkBtn}>Open live site</a>
                      )}
                      {page.status === 'completed' && page.src && (
                        <a href={page.src} target="_blank" rel="noopener noreferrer"
                          className={`${styles.webpageLinkBtn} ${styles.webpageLinkBtnGhost}`}>View archived</a>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            </section>
          )}

          {deleteError && <p className={styles.actionError}>{deleteError}</p>}
        </div>

        {trackVersions && (
          <aside className={`${styles.versionSidebar}${showVersionSidebar ? ` ${styles.versionSidebarOpen}` : ''}`}>
            <div className={styles.versionSidebarHeader}>
              <span>Version History</span>
              <button className={styles.versionSidebarClose} onClick={() => setShowVersionSidebar(false)}>✕</button>
            </div>
            {versions.length === 0 ? (
              <p className={styles.versionNoDiff}>No versions saved yet. Save the entry to record one.</p>
            ) : (
              <div className={styles.versionList}>
                {versions.map((version, idx) => {
                  const prev = versions[idx + 1] ?? null
                  const isExpanded = expandedVersionId === version.id
                  const bodyText = extractTextFromHtml(version.body as unknown)
                  const prevText = prev ? extractTextFromHtml(prev.body as unknown) : ''
                  const diff = isExpanded ? computeWordDiff(prevText, bodyText) : []
                  const addedMedia = isExpanded
                    ? version.media_refs.filter((r) => !prev?.media_refs.includes(r))
                    : []
                  const removedMedia = isExpanded
                    ? (prev?.media_refs ?? []).filter((r) => !version.media_refs.includes(r))
                    : []
                  return (
                    <article key={version.id} className={styles.versionCard}>
                      <button
                        className={styles.versionHeader}
                        onClick={() => setExpandedVersionId(isExpanded ? null : version.id)}
                      >
                        <span className={styles.versionTimestamp}>
                          {fmtDate(version.created_at)}
                        </span>
                        {idx === 0 && <span className={styles.versionBadge}>Latest</span>}
                        <span className={styles.versionChevron}>{isExpanded ? '▲' : '▼'}</span>
                      </button>
                      {isExpanded && (
                        <div className={styles.versionDiff}>
                          {diff.length === 0 && addedMedia.length === 0 && removedMedia.length === 0 && (
                            <p className={styles.versionNoDiff}>
                              {prev ? 'No text changes from previous version.' : 'Initial version.'}
                            </p>
                          )}
                          {diff.some((p) => p.type !== 'equal') && (
                            <div className={styles.versionDiffText}>
                              {diff.map((part, i) =>
                                part.type === 'equal' ? (
                                  <span key={i} className={styles.diffEqual}>{part.text}</span>
                                ) : part.type === 'added' ? (
                                  <ins key={i} className={styles.diffAdded}>{part.text}</ins>
                                ) : (
                                  <del key={i} className={styles.diffRemoved}>{part.text}</del>
                                )
                              )}
                            </div>
                          )}
                          {(addedMedia.length > 0 || removedMedia.length > 0) && (
                            <div className={styles.versionMediaChanges}>
                              {addedMedia.length > 0 && (
                                <p className={styles.versionMediaAdded}>
                                  +{addedMedia.length} file{addedMedia.length !== 1 ? 's' : ''} added
                                </p>
                              )}
                              {removedMedia.length > 0 && (
                                <p className={styles.versionMediaRemoved}>
                                  −{removedMedia.length} file{removedMedia.length !== 1 ? 's' : ''} removed
                                </p>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </article>
                  )
                })}
              </div>
            )}
          </aside>
        )}

        {bgAudioSrc && (
          <audio ref={bgAudioRef} src={bgAudioSrc} loop hidden />
        )}

        <div className={styles.actions}>
          <button className="btn btn-ghost" onClick={() => navigate(`/journals/${entry.journal_id}/`)}>
            ← Back
          </button>
          <button className="btn" onClick={() => {
            const query = new URLSearchParams({ journal: entry.journal_id })
            if (entryWorkspaceId) query.set('workspace', entryWorkspaceId)
            navigate(`/entries/${entry.id}/edit?${query.toString()}`, {
              state: entryWorkspaceId ? { workspaceId: entryWorkspaceId } : undefined,
            })
          }}>
            Edit
          </button>
          {isPrivilegedMode && (
            <button className="btn btn-ghost" onClick={() => {
              setShowMovePanel((prev) => {
                if (!prev) {
                  workspacesApi.list().then((r) => {
                    setMoveWorkspaces(r.data)
                    const first = r.data[0]
                    if (first) {
                      setMoveTargetWorkspaceId(first.id)
                      journalsApi.list(first.id).then((jr) => {
                        setMoveJournals(jr.data.filter((j: { id: string }) => j.id !== entry.journal_id))
                        setMoveTargetJournalId(jr.data.find((j: { id: string }) => j.id !== entry.journal_id)?.id ?? '')
                      }).catch(() => { })
                    }
                  }).catch(() => { })
                }
                return !prev
              })
            }}>↗ Move</button>
          )}
          {isPrivilegedMode && (
            <button className="btn btn-danger" disabled={deleting}
              onClick={() => void handleDelete()}>
              {deleting ? 'Moving…' : 'Move to Bin'}
            </button>
          )}
        </div>

        {isPrivilegedMode && showMovePanel && (
          <div className={`paper ${styles.movePanel}`}>
            <h3 className={styles.movePanelTitle}>Move Entry</h3>
            <div className={styles.moveRow}>
              <label className="label">Destination workspace</label>
              <select className="input" value={moveTargetWorkspaceId}
                onChange={(e) => {
                  const wsId = e.target.value
                  setMoveTargetWorkspaceId(wsId)
                  setMoveTargetJournalId('')
                  setMoveJournals([])
                  journalsApi.list(wsId).then((jr) => {
                    setMoveJournals(jr.data.filter((j: { id: string }) => j.id !== entry.journal_id))
                    setMoveTargetJournalId(jr.data.find((j: { id: string }) => j.id !== entry.journal_id)?.id ?? '')
                  }).catch(() => { })
                }}>
                {moveWorkspaces.map((ws) => <option key={ws.id} value={ws.id}>{ws.name}</option>)}
              </select>
            </div>
            <div className={styles.moveRow}>
              <label className="label">Destination journal</label>
              <select className="input" value={moveTargetJournalId}
                onChange={(e) => setMoveTargetJournalId(e.target.value)}>
                {moveJournals.length === 0
                  ? <option value="">No other journals available</option>
                  : moveJournals.map((j) => <option key={j.id} value={j.id}>{j.name}</option>)}
              </select>
            </div>
            {moveError && <p className="error-text">{moveError}</p>}
            <div className={styles.moveActions}>
              <button className="btn btn-ghost" onClick={() => setShowMovePanel(false)}>Cancel</button>
              <button className="btn" disabled={moving || !moveTargetJournalId}
                onClick={async () => {
                  if (!moveTargetJournalId) return
                  setMoving(true); setMoveError('')
                  try {
                    await entriesApi.move(entry.id, moveTargetJournalId)
                    navigate(`/journals/${moveTargetJournalId}`)
                  } catch (err: unknown) {
                    setMoveError(getApiErrorMessage(err, 'Failed to move entry.'))
                  } finally { setMoving(false) }
                }}>
                {moving ? 'Moving…' : 'Confirm Move'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
