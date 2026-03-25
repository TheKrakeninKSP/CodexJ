import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import ReactQuill from 'react-quill-new'
import type { Delta } from 'quill'
import 'react-quill-new/dist/quill.bubble.css'
import { entriesApi, type Entry } from '../services/api'
import styles from './EntryReader.module.css'

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
  const navigate = useNavigate()
  const [entry, setEntry] = useState<Entry | null>(null)
  const [loading, setLoading] = useState(true)
  const [durations, setDurations] = useState<Record<string, number>>({})

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

  if (loading) return <div className={styles.loading}>Loading…</div>
  if (!entry) return <div className={styles.loading}>Entry not found.</div>

  const audioSources = extractAudioSources(entry.body)

  return (
    <div className={styles.page}>
      <div className={`paper ${styles.article}`}>
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

        <div className={styles.body}>
          <ReactQuill
            value={entry.body as Delta}
            readOnly
            theme="bubble"
            modules={{ toolbar: false }}
          />
        </div>

        {audioSources.length > 0 && (
          <section className={styles.audioSection}>
            <h3>Audio</h3>
            <div className={styles.audioList}>
              {audioSources.map((source) => (
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
              ))}
            </div>
          </section>
        )}
      </div>

      <div className={styles.actions}>
        <button className="btn btn-ghost" onClick={() => navigate(`/journals/${entry.journal_id}/`)}>
          ← Back
        </button>
        <button className="btn" onClick={() => navigate(`/entries/${entry.id}/edit`)}>
          Edit
        </button>
        <button
          className="btn btn-danger"
          onClick={async () => {
            if (!confirm('Delete this entry?')) return
            await entriesApi.remove(entry.id)
            navigate(-1)
          }}
        >
          Delete
        </button>
      </div>
    </div>
  )
}
