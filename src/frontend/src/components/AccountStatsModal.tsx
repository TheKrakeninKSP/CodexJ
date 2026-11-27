import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { authApi, type AccountStats } from '../services/api'
import { getApiErrorMessage } from '../utils/errors'
import { parseApiDate } from '../utils/datetime'
import { formatBytes } from '../utils/format'
import styles from './AccountStatsModal.module.css'

type Props = {
  username: string | null
  onClose: () => void
}

const COUNT_TILES: { key: keyof AccountStats; label: string }[] = [
  { key: 'entry_count', label: 'Entries' },
  { key: 'journal_count', label: 'Journals' },
  { key: 'workspace_count', label: 'Workspaces' },
  { key: 'tag_count', label: 'Tags' },
  { key: 'media_count', label: 'Media' },
]

export default function AccountStatsModal({ username, onClose }: Props) {
  const [stats, setStats] = useState<AccountStats | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    authApi
      .myStats()
      .then((res) => { if (!cancelled) setStats(res.data) })
      .catch((err: unknown) => {
        if (!cancelled) setError(getApiErrorMessage(err, 'Could not load account stats.'))
      })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // Portalled to <body>: the mobile sidebar drawer is transformed, which would
  // otherwise trap a position:fixed overlay inside it.
  return createPortal(
    <div className={styles.backdrop} onClick={onClose}>
      <div
        className={`paper ${styles.dialog}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="account-stats-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.header}>
          <h2 id="account-stats-title" className={styles.title}>✦ {username}</h2>
          <button className="btn btn-ghost" onClick={onClose} aria-label="Close">✕</button>
        </div>

        {error && <p className={styles.error}>{error}</p>}
        {!error && !stats && <p className={styles.muted}>Loading…</p>}

        {stats && (
          <>
            <p className={styles.since}>
              Member since{' '}
              {parseApiDate(stats.created_at).toLocaleDateString(undefined, {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
              })}
            </p>

            <div className={styles.tiles}>
              {COUNT_TILES.map(({ key, label }) => (
                <div key={key} className={styles.tile}>
                  <span className={styles.tileValue}>
                    {(stats[key] as number).toLocaleString()}
                  </span>
                  <span className={styles.tileLabel}>{label}</span>
                </div>
              ))}
            </div>

            <div className={styles.storage}>
              <div className={styles.storageRow}>
                <span className={styles.tileLabel}>Storage used</span>
                <span className={styles.storageTotal}>{formatBytes(stats.total_bytes)}</span>
              </div>
              <p className={styles.muted}>
                {formatBytes(stats.media_bytes)} media · {formatBytes(stats.text_bytes)} text
              </p>
            </div>

            <p className={styles.hint}>
              Counts exclude items in the bin; storage includes them.
            </p>
          </>
        )}
      </div>
    </div>,
    document.body,
  )
}
