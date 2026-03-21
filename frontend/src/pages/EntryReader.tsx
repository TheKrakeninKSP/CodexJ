import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import ReactQuill from 'react-quill-new'
import type { Delta } from 'quill'
import 'react-quill-new/dist/quill.bubble.css'
import { entriesApi, type Entry } from '../services/api'
import styles from './EntryReader.module.css'

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
  })
}

export default function EntryReader() {
  const { entryId } = useParams<{ entryId: string }>()
  const navigate = useNavigate()
  const [entry, setEntry] = useState<Entry | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!entryId) return
    entriesApi.get(entryId).then((r) => {
      setEntry(r.data)
      setLoading(false)
    })
  }, [entryId])

  if (loading) return <div className={styles.loading}>Loading…</div>
  if (!entry) return <div className={styles.loading}>Entry not found.</div>

  return (
    <div className={styles.page}>
      <div className={`paper ${styles.article}`}>
        <div className={styles.meta}>
          <span className={styles.date}>{fmtDate(entry.date_created)}</span>
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
