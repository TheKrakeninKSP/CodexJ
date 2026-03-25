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

export default function EntryReader() {
  const { entryId } = useParams<{ entryId: string }>()
  const navigate = useNavigate()
  const [entry, setEntry] = useState<Entry | null>(null)
  const [loading, setLoading] = useState(true)

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
