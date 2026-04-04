import { useEffect, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import ReactQuill from 'react-quill-new'
import type { Delta } from 'quill'
import 'react-quill-new/dist/quill.bubble.css'
import { entriesApi, mediaApi, type Entry, type MediaRecord, type MusicInfo } from '../services/api'
import { useAuthStore } from '../stores/authStore'
import { useWorkspaceStore } from '../stores/workspaceStore'
import {
  extractWebpageEmbeds,
  getWebpageSourceLabel,
  listPendingWebpageResourcePaths,
  syncWebpageEmbedsWithMedia,
  type WebpageEmbedValue,
} from '../utils/webpageEmbeds'
import styles from './EntryReader.module.css'

const readerQuill = (ReactQuill as unknown as { Quill: any }).Quill
const ReaderBaseBlockEmbed = readerQuill.import('blots/block/embed')

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

const AUDIO_EXTENSIONS = new Set([
  '.mp3',
  '.aac',
  '.flac',
  '.wav',
  '.m4a',
  '.ogg',
  '.oga',
  '.alac',
])

function isAudioUrl(raw: string): boolean {
  if (!raw) return false
  try {
    const url = new URL(raw, window.location.origin)
    const pathname = url.pathname.toLowerCase()
    return Array.from(AUDIO_EXTENSIONS).some((ext) => pathname.endsWith(ext))
  } catch {
    return false
  }
}

interface AudioSource {
  src: string
  originalFilename?: string
}

const SHOW_AUDIO_INLINE_KEY = 'show-audio-inline'
const SHOW_URLS_INLINE_KEY = 'show-urls-inline'
const IDENTIFY_AUDIO_KEY = 'identify-audio'

function shouldShowAudioInline(metadata: Entry['custom_metadata']): boolean {
  const match = metadata.find((field) => field.key === SHOW_AUDIO_INLINE_KEY)
  if (!match) return false
  const normalized = match.value.trim().toLowerCase()
  return ['true', '1', 'yes', 'on'].includes(normalized)
}

function shouldShowUrlsInline(metadata: Entry['custom_metadata']): boolean {
  const match = metadata.find((field) => field.key === SHOW_URLS_INLINE_KEY)
  if (!match) return false
  const normalized = match.value.trim().toLowerCase()
  return ['true', '1', 'yes', 'on'].includes(normalized)
}

function shouldShowRichAudio(metadata: Entry['custom_metadata']): boolean {
  const match = metadata.find((field) => field.key === IDENTIFY_AUDIO_KEY)
  if (!match) return false
  const normalized = match.value.trim().toLowerCase()
  return ['true', '1', 'yes', 'on'].includes(normalized)
}

function hasLiveSourceUrl(sourceUrl: string): boolean {
  return /^https?:\/\//i.test(sourceUrl.trim())
}

class WebpageBlot extends ReaderBaseBlockEmbed {
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

    const actions = document.createElement('div')
    actions.className = 'ql-webpage-actions'

    const statusEl = document.createElement('div')
    statusEl.className = 'ql-webpage-status'

    info.appendChild(titleEl)
    info.appendChild(urlEl)

    if (status === 'pending') {
      node.classList.add('ql-webpage-pending')
      statusEl.textContent = 'Archiving in background'
      info.appendChild(statusEl)
    } else if (status === 'failed') {
      node.classList.add('ql-webpage-failed')
      statusEl.textContent = value.error_message || 'Archive failed'
      info.appendChild(statusEl)
    }

    if (hasLiveSourceUrl(value.source_url)) {
      const liveLink = document.createElement('a')
      liveLink.className = 'ql-webpage-linkbtn'
      liveLink.href = value.source_url
      liveLink.target = '_blank'
      liveLink.rel = 'noopener noreferrer'
      liveLink.textContent = 'Open live site'
      actions.appendChild(liveLink)
    }
    if (status === 'completed' && value.src) {
      const archivedLink = document.createElement('a')
      archivedLink.className = 'ql-webpage-linkbtn ql-webpage-linkbtn-ghost'
      archivedLink.href = value.src
      archivedLink.target = '_blank'
      archivedLink.rel = 'noopener noreferrer'
      archivedLink.textContent = 'View archived'
      actions.appendChild(archivedLink)
    }
    node.appendChild(icon)
    node.appendChild(info)
    node.appendChild(actions)
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

if (!readerQuill.imports['formats/webpage']) {
  readerQuill.register(WebpageBlot)
}

function extractAudioSources(body: Entry['body']): AudioSource[] {
  if (!body || typeof body !== 'object' || !('ops' in body)) return []

  const ops = (body as { ops?: unknown }).ops
  if (!Array.isArray(ops)) return []

  const sources = new Map<string, AudioSource>()

  for (const op of ops) {
    if (!op || typeof op !== 'object') continue

    const insert = (op as { insert?: unknown }).insert
    if (insert && typeof insert === 'object') {
      const audio = (insert as { audio?: unknown }).audio
      if (typeof audio === 'string' && isAudioUrl(audio)) {
        sources.set(audio, { src: audio })
      }
      if (audio && typeof audio === 'object') {
        const src = (audio as { src?: unknown; url?: unknown }).src
          ?? (audio as { src?: unknown; url?: unknown }).url
        const originalFilename = (audio as { original_filename?: unknown }).original_filename
        if (typeof src === 'string' && isAudioUrl(src)) {
          sources.set(src, {
            src,
            originalFilename: typeof originalFilename === 'string' ? originalFilename : undefined,
          })
        }
      }
      continue
    }

    const attributes = (op as { attributes?: unknown }).attributes
    if (attributes && typeof attributes === 'object') {
      const link = (attributes as { link?: unknown }).link
      if (typeof link === 'string' && isAudioUrl(link)) {
        sources.set(link, { src: link })
      }
    }

    if (typeof insert === 'string' && isAudioUrl(insert.trim())) {
      const src = insert.trim()
      sources.set(src, { src })
    }
  }

  return Array.from(sources.values())
}

function removeWebpageEmbeds(body: Entry['body']): Entry['body'] {
  if (!body || typeof body !== 'object' || !('ops' in body)) {
    return { ops: [] }
  }

  const ops = (body as { ops?: unknown }).ops
  if (!Array.isArray(ops)) {
    return { ops: [] }
  }

  const filteredOps = ops.filter((op) => {
    if (!op || typeof op !== 'object') return true
    const insert = (op as { insert?: unknown }).insert
    return !(insert && typeof insert === 'object' && 'webpage' in insert)
  })

  if (filteredOps.length === 0) {
    return { ops: [{ insert: '\n' }] }
  }

  return { ops: filteredOps }
}

function getFileExtension(raw: string): string {
  try {
    const url = new URL(raw, window.location.origin)
    const pathname = url.pathname
    const lastDot = pathname.lastIndexOf('.')
    if (lastDot === -1) return 'AUDIO'
    return pathname.slice(lastDot + 1).toUpperCase() || 'AUDIO'
  } catch {
    return 'AUDIO'
  }
}

function getFileName(raw: string): string {
  try {
    const url = new URL(raw, window.location.origin)
    const base = url.pathname.split('/').filter(Boolean).pop() ?? raw
    return decodeURIComponent(base)
  } catch {
    return raw
  }
}

function formatDuration(seconds?: number): string {
  if (!seconds || Number.isNaN(seconds) || !Number.isFinite(seconds)) return '--:--'
  const total = Math.max(0, Math.round(seconds))
  const mins = Math.floor(total / 60)
  const secs = total % 60
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

function getDisplayName(source: AudioSource): string {
  const original = source.originalFilename?.trim()
  if (original) return original
  return getFileName(source.src)
}

export default function EntryReader() {
  const { entryId } = useParams<{ entryId: string }>()
  const location = useLocation()
  const navigate = useNavigate()
  const [entry, setEntry] = useState<Entry | null>(null)
  const [loading, setLoading] = useState(true)
  const [deleteError, setDeleteError] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [durations, setDurations] = useState<Record<string, number>>({})
  const [audioMediaInfo, setAudioMediaInfo] = useState<Record<string, MediaRecord>>({})

  const isPrivilegedMode = useAuthStore((s) => s.isPrivilegedMode)
  const activeJournal = useWorkspaceStore((s) => s.activeJournal)
  const journals = useWorkspaceStore((s) => s.journals)

  useEffect(() => {
    if (!entryId) return
    entriesApi.get(entryId)
      .then((r) => {
        setEntry(r.data)
        setLoading(false)
      })
      .catch((err) => {
        console.error('Failed to load entry:', err)
        setLoading(false)
      })
  }, [entryId])

  useEffect(() => {
    if (!entry) return

    const pendingWebpagePaths = listPendingWebpageResourcePaths(entry.body)
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
        setEntry((currentEntry) => {
          if (!currentEntry) return currentEntry
          const nextBody = syncWebpageEmbedsWithMedia(currentEntry.body, mediaByPath)
          if (nextBody === currentEntry.body) return currentEntry
          return {
            ...currentEntry,
            body: nextBody,
          }
        })
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
  }, [entry])

  // Fetch music identification metadata for audio sources
  useEffect(() => {
    if (!entry) return
    const sources = extractAudioSources(entry.body)
    if (sources.length === 0) return

    let cancelled = false

    const fetchAudioMediaInfo = async () => {
      for (const source of sources) {
        if (cancelled) break
        if (audioMediaInfo[source.src]) continue
        try {
          const res = await mediaApi.getStatus(source.src)
          if (!cancelled) {
            setAudioMediaInfo((prev) => ({ ...prev, [source.src]: res.data }))
          }
        } catch {
          // Media record not found — skip
        }
      }
    }

    void fetchAudioMediaInfo()
    return () => { cancelled = true }
  }, [entry])

  // Poll for pending music lookups
  useEffect(() => {
    const pendingSources = Object.entries(audioMediaInfo)
      .filter(([, media]) => {
        const status = (media.custom_metadata as Record<string, unknown> | null)?.music_lookup_status
        return status === 'pending'
      })
      .map(([src]) => src)

    if (pendingSources.length === 0) return

    let cancelled = false

    const poll = async () => {
      for (const src of pendingSources) {
        if (cancelled) break
        try {
          const res = await mediaApi.getStatus(src)
          if (!cancelled) {
            setAudioMediaInfo((prev) => ({ ...prev, [src]: res.data }))
          }
        } catch {
          // ignore
        }
      }
    }

    const intervalId = window.setInterval(() => { void poll() }, 3000)
    return () => {
      cancelled = true
      window.clearInterval(intervalId)
    }
  }, [audioMediaInfo])

  if (loading) return <div className={styles.loading}>Loading…</div>
  if (!entry) return <div className={styles.loading}>Entry not found.</div>

  const audioSources = extractAudioSources(entry.body)
  const webpageSources = extractWebpageEmbeds(entry.body)
  const showAudioInline = shouldShowAudioInline(entry.custom_metadata)
  const showRichAudio = shouldShowRichAudio(entry.custom_metadata)

  const getMusicInfo = (src: string): MusicInfo | null => {
    const media = audioMediaInfo[src]
    if (!media?.custom_metadata) return null
    const info = (media.custom_metadata as Record<string, unknown>).music_info
    if (!info || typeof info !== 'object') return null
    return info as MusicInfo
  }

  const showUrlsInline = shouldShowUrlsInline(entry.custom_metadata)
  const entryTitle = entry.name?.trim() || fmtDate(entry.date_created, entry.timezone)
  const displayBody = showUrlsInline ? entry.body : removeWebpageEmbeds(entry.body)
  const locationWorkspaceId =
    ((location.state as { workspaceId?: string } | null)?.workspaceId ?? '')
  const entryWorkspaceId =
    locationWorkspaceId
    || (activeJournal?.id === entry.journal_id ? activeJournal.workspace_id : '')
    || journals.find((journal) => journal.id === entry.journal_id)?.workspace_id
    || ''
  const canNavigateBack =
    typeof window !== 'undefined'
    && typeof window.history.state?.idx === 'number'
    && window.history.state.idx > 0

  const handleBack = () => {
    if (canNavigateBack) {
      navigate(-1)
      return
    }

    navigate(`/journals/${entry.journal_id}/`, {
      state: entryWorkspaceId ? { workspaceId: entryWorkspaceId } : undefined,
    })
  }

  const handleBodyClick = (event: React.MouseEvent<HTMLDivElement>) => {
    if (event.defaultPrevented || event.button !== 0) return
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    if (!(event.target instanceof Element)) return

    const anchor = event.target.closest('a')
    if (!(anchor instanceof HTMLAnchorElement)) return

    const href = anchor.getAttribute('href')
    if (!href) return

    let url: URL
    try {
      url = new URL(href, window.location.href)
    } catch {
      return
    }

    if (url.origin !== window.location.origin) return
    if (!/^\/entries\/[^/]+\/?$/.test(url.pathname)) return

    event.preventDefault()
    navigate(`${url.pathname}${url.search}${url.hash}`)
  }

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

  const handleDelete = async () => {
    setDeleteError('')
    setDeleting(true)
    try {
      await entriesApi.remove(entry.id)
      window.dispatchEvent(new Event('codexj-bin-changed'))
      handleBack()
    } catch (err: unknown) {
      setDeleteError(getApiErrorMessage(err, 'Could not move entry to Bin.'))
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className={styles.page}>
      <div className={`paper ${styles.article}`}>
        <h1 className={styles.entryTitle}>{entryTitle}</h1>
        <div className={styles.meta}>
          <span className={styles.date}>{fmtDate(entry.date_created, entry.timezone)}</span>
          <span className={styles.type}>{entry.type}</span>
        </div>

        {entry.custom_metadata.length > 0 && (
          <details className={styles.customMeta}>
            <summary>Additional info</summary>
            <table className={styles.metaTable}>
              <tbody>
                {entry.custom_metadata.map((f, i) => (
                  <tr key={i}>
                    <td className={styles.metaKey}>{f.key}</td>
                    <td>{f.value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        )}

        <div
          className={showAudioInline ? styles.body : `${styles.body} ${styles.hideInlineAudio}`}
          onClick={handleBodyClick}
        >
          <ReactQuill
            value={displayBody as Delta}
            readOnly
            theme="bubble"
            modules={{ toolbar: false }}
          />
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
                          {musicInfo.artist && (
                            <p className={styles.musicArtist}>{musicInfo.artist}</p>
                          )}
                          <div className={styles.musicDetails}>
                            {musicInfo.album && (
                              <span className={styles.musicAlbum}>{musicInfo.album}</span>
                            )}
                            {musicInfo.year && (
                              <span className={styles.musicYear}>{musicInfo.year}</span>
                            )}
                          </div>
                        </div>
                      </div>
                      <audio
                        controls
                        preload="metadata"
                        src={source.src}
                        className={styles.audioPlayer}
                        onLoadedMetadata={(event) => {
                          const duration = event.currentTarget.duration
                          if (!duration || Number.isNaN(duration) || !Number.isFinite(duration)) return
                          setDurations((prev) => ({ ...prev, [source.src]: duration }))
                        }}
                      >
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
                    <audio
                      controls
                      preload="metadata"
                      src={source.src}
                      className={styles.audioPlayer}
                      onLoadedMetadata={(event) => {
                        const duration = event.currentTarget.duration
                        if (!duration || Number.isNaN(duration) || !Number.isFinite(duration)) return
                        setDurations((prev) => ({ ...prev, [source.src]: duration }))
                      }}
                    >
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
              {webpageSources.map((page) => (
                <article key={page.src} className={styles.webpageCard}>
                  <div className={styles.webpageIcon}>🌐︎</div>
                  <div className={styles.webpageInfo}>
                    <p className={styles.webpageTitle}>
                      {page.status === 'pending'
                        ? 'Archiving webpage…'
                        : page.title || getWebpageSourceLabel(page.source_url)}
                    </p>
                    <p className={styles.webpageUrl}>{getWebpageSourceLabel(page.source_url)}</p>
                    {page.status === 'pending' && (
                      <p className={styles.webpageStatus}>Archiving in background</p>
                    )}
                    {page.status === 'failed' && (
                      <p className={`${styles.webpageStatus} ${styles.webpageStatusError}`}>
                        {page.error_message || 'Archive failed'}
                      </p>
                    )}
                  </div>
                  <div className={styles.webpageActions}>
                    {hasLiveSourceUrl(page.source_url) && (
                      <a
                        href={page.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={styles.webpageLinkBtn}
                      >
                        Open live site
                      </a>
                    )}
                    {page.status === 'completed' && page.src && (
                      <a
                        href={page.src}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={`${styles.webpageLinkBtn} ${styles.webpageLinkBtnGhost}`}
                      >
                        View archived
                      </a>
                    )}
                  </div>
                </article>
              ))}
            </div>
          </section>
        )}

        {deleteError && <p className={styles.actionError}>{deleteError}</p>}
      </div>

      <div className={styles.actions}>
        <button className="btn btn-ghost" onClick={handleBack}>
          ← Back
        </button>
        <button
          className="btn"
          onClick={() => {
            const query = new URLSearchParams({ journal: entry.journal_id })
            if (entryWorkspaceId) query.set('workspace', entryWorkspaceId)
            navigate(`/entries/${entry.id}/edit?${query.toString()}`, {
              state: entryWorkspaceId ? { workspaceId: entryWorkspaceId } : undefined,
            })
          }}
        >
          Edit
        </button>
        {isPrivilegedMode && (
          <button
            className="btn btn-danger"
            disabled={deleting}
            onClick={() => void handleDelete()}
          >
            {deleting ? 'Moving…' : 'Move to Bin'}
          </button>
        )}
      </div>
    </div>
  )
}
