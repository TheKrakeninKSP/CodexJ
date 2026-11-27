import { useCallback, useEffect, useMemo, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { adminApi, type AdminOverview, type AdminUserStats } from '../services/api'
import { useAuthStore } from '../stores/authStore'
import { getApiErrorMessage } from '../utils/errors'
import { formatBytes } from '../utils/format'
import styles from './AdminDashboard.module.css'

type SortKey = 'username' | 'total_bytes' | 'entry_count' | 'last_login_at' | 'created_at'

const SORT_DEFAULT_DESC: Record<SortKey, boolean> = {
  username: false,
  total_bytes: true,
  entry_count: true,
  last_login_at: true,
  created_at: true,
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatRelative(iso: string): string {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
  const steps: [number, Intl.RelativeTimeFormatUnit][] = [
    [60, 'second'],
    [60, 'minute'],
    [24, 'hour'],
    [30, 'day'],
    [12, 'month'],
    [Infinity, 'year'],
  ]
  let value = seconds
  for (const [size, unit] of steps) {
    if (Math.abs(value) < size) return rtf.format(-Math.round(value), unit)
    value /= size
  }
  return formatDate(iso)
}

function compareUsers(a: AdminUserStats, b: AdminUserStats, key: SortKey): number {
  if (key === 'username') return a.username.localeCompare(b.username)
  if (key === 'last_login_at' || key === 'created_at') {
    // Never-logged-in users sort as oldest.
    const av = a[key] ? new Date(a[key] as string).getTime() : 0
    const bv = b[key] ? new Date(b[key] as string).getTime() : 0
    return av - bv
  }
  return a[key] - b[key]
}

export default function AdminDashboard() {
  const isAdmin = useAuthStore((s) => s.isAdmin)
  const [data, setData] = useState<AdminOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('total_bytes')
  const [sortDesc, setSortDesc] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    adminApi.overview()
      .then((r) => setData(r.data))
      .catch((err: unknown) => setError(getApiErrorMessage(err, 'Could not load admin overview.')))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (isAdmin) load()
  }, [isAdmin, load])

  const users = useMemo(() => {
    if (!data) return []
    const sorted = [...data.users].sort((a, b) => compareUsers(a, b, sortKey))
    return sortDesc ? sorted.reverse() : sorted
  }, [data, sortKey, sortDesc])

  // isAdmin is fetched after login; a non-admin landing here (typed URL) goes home.
  if (!isAdmin) return <Navigate to="/" replace />

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDesc((d) => !d)
    } else {
      setSortKey(key)
      setSortDesc(SORT_DEFAULT_DESC[key])
    }
  }

  const sortHeader = (key: SortKey, label: string, numeric = false) => (
    <th
      scope="col"
      className={numeric ? styles.num : undefined}
      aria-sort={sortKey === key ? (sortDesc ? 'descending' : 'ascending') : 'none'}
    >
      <button type="button" className={styles.sortButton} onClick={() => handleSort(key)}>
        {label}
        <span className={styles.sortArrow} aria-hidden="true">
          {sortKey === key ? (sortDesc ? '▾' : '▴') : ''}
        </span>
      </button>
    </th>
  )

  const maxTotal = Math.max(1, ...users.map((u) => u.total_bytes))

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.heading}>Admin</h1>
          <p className={styles.sub}>Accounts and storage on this server.</p>
        </div>
        <button type="button" className="btn btn-ghost" onClick={load} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {error && <p className={styles.error}>{error}</p>}

      {data && (
        <>
          <div className={styles.tiles}>
            <div className={`paper ${styles.tile}`}>
              <span className={styles.tileLabel}>Users</span>
              <span className={styles.tileValue}>{data.user_count}</span>
            </div>
            <div className={`paper ${styles.tile}`}>
              <span className={styles.tileLabel}>Total storage</span>
              <span className={styles.tileValue}>{formatBytes(data.total_bytes)}</span>
            </div>
            <div className={`paper ${styles.tile}`}>
              <span className={styles.tileLabel}>Media files</span>
              <span className={styles.tileValue}>{formatBytes(data.total_media_bytes)}</span>
            </div>
            <div className={`paper ${styles.tile}`}>
              <span className={styles.tileLabel}>Entry text</span>
              <span className={styles.tileValue}>{formatBytes(data.total_text_bytes)}</span>
            </div>
          </div>

          <div className={`paper ${styles.tableWrap}`}>
            <table className={styles.table}>
              <thead>
                <tr>
                  {sortHeader('username', 'User')}
                  {sortHeader('total_bytes', 'Storage', true)}
                  {sortHeader('entry_count', 'Entries', true)}
                  {sortHeader('last_login_at', 'Last login')}
                  {sortHeader('created_at', 'Created')}
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td data-label="User" className={styles.userCell}>
                      <span className={styles.userInner}>
                        <span className={styles.username}>{u.username}</span>
                        {u.is_admin && <span className={styles.badge}>admin</span>}
                      </span>
                    </td>
                    <td data-label="Storage" className={styles.num}>
                      <span className={styles.storageTotal}>{formatBytes(u.total_bytes)}</span>
                      <span className={styles.bar} aria-hidden="true">
                        <span
                          className={styles.barFill}
                          style={{ width: `${(u.total_bytes / maxTotal) * 100}%` }}
                        />
                      </span>
                      <span className={styles.storageDetail}>
                        {formatBytes(u.media_bytes)} media · {u.media_files} file{u.media_files === 1 ? '' : 's'}
                        {' · '}
                        {formatBytes(u.text_bytes)} text
                      </span>
                    </td>
                    <td data-label="Entries" className={styles.num}>{u.entry_count}</td>
                    <td data-label="Last login">
                      {u.last_login_at ? (
                        <time dateTime={u.last_login_at} title={formatDate(u.last_login_at)}>
                          {formatRelative(u.last_login_at)}
                        </time>
                      ) : (
                        <span className={styles.muted}>Never recorded</span>
                      )}
                    </td>
                    <td data-label="Created">
                      <time dateTime={u.created_at}>{formatDate(u.created_at)}</time>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className={styles.hint}>
            Media is the on-disk size of each user's media folder, including files no entry
            references any more. Text counts entry bodies, metadata, and saved versions.
          </p>
        </>
      )}

      {!data && loading && <p className={styles.hint}>Loading…</p>}
    </div>
  )
}
