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
export default function MusicTagPanel({ entryId, onQueued }: Props) {
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

  return (
    <section className={styles.panel}>
      <div>
        <p className={styles.title}>Tag a song</p>
        <p className={styles.hint}>
          Search for a track and pick it. Its audio is downloaded from the top YouTube
          match in the background and attached to this entry with its MusicBrainz details.
        </p>
      </div>
      <div className={styles.row}>
        <input className={`input ${styles.input}`} placeholder="Song title"
          value={title} onChange={(e) => setTitle(e.target.value)} disabled={busy}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); void search() } }} />
        <input className={`input ${styles.input}`} placeholder="Artist (optional, improves results)"
          value={artist} onChange={(e) => setArtist(e.target.value)} disabled={busy}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); void search() } }} />
        <button className="btn btn-ghost" type="button"
          disabled={searching || busy || !title.trim()} onClick={() => void search()}>
          {searching ? 'Searching…' : 'Search'}
        </button>
      </div>
      {error && <p className="error-text">{error}</p>}
      {results && results.length === 0 && (
        <p className={styles.status}>No matches on MusicBrainz.</p>
      )}
      {results && results.length > 0 && (
        <div className={styles.results}>
          {results.map((r) => (
            <button key={r.mbid} type="button" disabled={busy}
              className={`${styles.result} ${starting === r.mbid ? styles.resultSelected : ''}`}
              onClick={() => void download(r.mbid, {
                title: r.title, artist: r.artist, album: r.album, year: r.year,
                mbid: r.mbid, release_mbid: r.release_mbid,
              })}>
              <Cover releaseMbid={r.release_mbid} />
              <div className={styles.resultMeta}>
                <p className={styles.resultTitle}>{r.title}</p>
                <p className={styles.resultSub}>
                  {[r.artist, r.album, r.year].filter(Boolean).join(' · ')}
                </p>
              </div>
              {starting === r.mbid && <span className={styles.status}>Starting…</span>}
            </button>
          ))}
        </div>
      )}
      {results && title.trim() && (
        <button className="btn btn-ghost" type="button" disabled={busy}
          style={{ alignSelf: 'flex-start' }}
          onClick={() => void download('typed', { title: title.trim(), artist: artist.trim() })}>
          {starting === 'typed' ? 'Starting…' : `Not listed? Download “${typedLabel}” as typed`}
        </button>
      )}
    </section>
  )
}
