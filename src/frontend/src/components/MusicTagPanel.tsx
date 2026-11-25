import { useState } from 'react'
import {
  musicApi,
  type MediaRecord,
  type MusicDownloadRequest,
  type MusicSearchResult,
} from '../services/api'
import { getApiErrorMessage } from '../utils/errors'
import styles from './MusicTagPanel.module.css'

interface Props {
  entryId: string
  /** Called once the server has queued the download; `label` is a display name for it. */
  onQueued: (media: MediaRecord, label: string) => void
  /** Esc in the search fields */
  onClose: () => void
}

function Cover({ releaseMbid }: { releaseMbid: string | null }) {
  const [failed, setFailed] = useState(false)
  if (!releaseMbid || failed) return <div className={styles.coverPlaceholder}>♫</div>
  return (
    <img className={styles.cover} alt="" loading="lazy"
      src={`https://coverartarchive.org/release/${releaseMbid}/front-250`}
      onError={() => setFailed(true)} />
  )
}

/**
 * Tag a song onto an entry without having its audio: search MusicBrainz for the track,
 * and on pick the server downloads the audio of the top YouTube match (yt-dlp -x) in
 * the background. The result is an ordinary audio media item, so it gets the usual rich
 * audio card; the editor shows a placeholder until the download finishes.
 */
export default function MusicTagPanel({ entryId, onQueued, onClose }: Props) {
  const [title, setTitle] = useState('')
  const [artist, setArtist] = useState('')
  const [searching, setSearching] = useState(false)
  const [results, setResults] = useState<MusicSearchResult[] | null>(null)
  // Key of the row whose download is being queued ('typed' for the use-as-typed fallback)
  const [starting, setStarting] = useState<string | null>(null)
  const [error, setError] = useState('')

  const search = async () => {
    if (!title.trim() || starting) return
    setSearching(true)
    setError('')
    try {
      const res = await musicApi.search(title.trim(), artist.trim() || undefined)
      setResults(res.data)
    } catch (err) {
      setError(getApiErrorMessage(err, 'Music search failed.'))
      setResults(null)
    } finally {
      setSearching(false)
    }
  }

  // Only queues the download (returns immediately); the editor tracks it from here.
  const download = async (key: string, payload: Omit<MusicDownloadRequest, 'entry_id'>) => {
    setStarting(key)
    setError('')
    try {
      const res = await musicApi.download({ entry_id: entryId, ...payload })
      onQueued(res.data, [payload.artist, payload.title].filter(Boolean).join(' – '))
    } catch (err) {
      setError(getApiErrorMessage(err, 'Could not start the download.'))
    } finally {
      setStarting(null)
    }
  }

  const busy = starting !== null
  const typedLabel = `${title.trim()}${artist.trim() ? ` – ${artist.trim()}` : ''}`

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') { e.preventDefault(); void search() }
    else if (e.key === 'Escape') { e.preventDefault(); onClose() }
  }

  return (
    <section className={styles.bar} aria-label="Tag a song">
      <div className={styles.row}>
        <input className={styles.input} autoFocus placeholder="Song title"
          aria-label="Song title"
          value={title} onChange={(e) => setTitle(e.target.value)} disabled={busy}
          onKeyDown={handleKeyDown} />
        <input className={styles.input} placeholder="Artist (optional)"
          aria-label="Artist"
          value={artist} onChange={(e) => setArtist(e.target.value)} disabled={busy}
          onKeyDown={handleKeyDown} />
        <button className="btn" type="button"
          disabled={searching || busy || !title.trim()} onClick={() => void search()}>
          {searching ? 'Searching…' : 'Search'}
        </button>
      </div>
      {error && <p className={`error-text ${styles.status}`}>{error}</p>}
      {results && results.length === 0 && (
        <p className={styles.status}>No matches on MusicBrainz</p>
      )}
      {results && results.length > 0 && (
        <ul className={styles.results} aria-label="Matching songs">
          {results.map((r) => (
            <li key={r.mbid}>
              <button type="button" disabled={busy}
                className={`${styles.result} ${starting === r.mbid ? styles.resultSelected : ''}`}
                title="Download this song's audio from YouTube into the entry"
                onClick={() => void download(r.mbid, {
                  title: r.title, artist: r.artist, album: r.album, year: r.year,
                  mbid: r.mbid, release_mbid: r.release_mbid,
                })}>
                <Cover releaseMbid={r.release_mbid} />
                <span className={styles.resultTitle}>{r.title}</span>
                <span className={styles.resultSub}>
                  {[r.artist, r.album, r.year].filter(Boolean).join(' · ')}
                </span>
                {starting === r.mbid && <span className={styles.status}>Starting…</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
      {results && title.trim() && (
        <button className={styles.typedBtn} type="button" disabled={busy}
          onClick={() => void download('typed', { title: title.trim(), artist: artist.trim() })}>
          {starting === 'typed' ? 'Starting…' : `Not listed? Download “${typedLabel}” as typed`}
        </button>
      )}
    </section>
  )
}
