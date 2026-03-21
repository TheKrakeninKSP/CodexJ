import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import ReactQuill, { type ReactQuillProps, type UnprivilegedEditor } from 'react-quill-new'
import 'react-quill-new/dist/quill.snow.css'
import {
  entriesApi,
  entryTypesApi,
  mediaApi,
  type EntryType,
  type MetadataField,
} from '../services/api'
import styles from './EntryEditor.module.css'

export default function EntryEditor() {
  const { entryId } = useParams<{ entryId: string }>()
  const [searchParams] = useSearchParams()
  const journalId = searchParams.get('journal') ?? ''
  const navigate = useNavigate()

  const quillRef = useRef<ReactQuill>(null)

  const [entryTypes, setEntryTypes] = useState<EntryType[]>([])
  const [selectedType, setSelectedType] = useState('')
  const [entryName, setEntryName] = useState('')
  const [customMetadata, setCustomMetadata] = useState<MetadataField[]>([])
  const [body, setBody] = useState<object>({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  // Load existing entry when editing
  useEffect(() => {
    if (entryId) {
      entriesApi.get(entryId).then((r) => {
        setSelectedType(r.data.type)
        setEntryName(r.data.name)
        setCustomMetadata(r.data.custom_metadata)
        setBody(r.data.body)
      })
    }
    entryTypesApi.list().then((r) => setEntryTypes(r.data))
  }, [entryId])

  // Custom image handler: upload to Cloudinary via backend, insert URL
  const imageHandler = () => {
    const input = document.createElement('input')
    input.setAttribute('type', 'file')
    input.setAttribute('accept', 'image/*,video/*')
    input.click()
    input.onchange = async () => {
      const file = input.files?.[0]
      if (!file || !quillRef.current) return
      const quill = quillRef.current.getEditor()
      const range = quill.getSelection(true)
      try {
        const res = await mediaApi.upload(file)
        const url = res.data.resource_path
        if (res.data.resource_type === 'video') {
          quill.insertEmbed(range.index, 'video', url)
        } else {
          quill.insertEmbed(range.index, 'image', url)
        }
        quill.setSelection(range.index + 1, 0)
      } catch {
        alert('Media upload failed.')
      }
    }
  }

  const modules = useMemo(
    () => ({
      toolbar: {
        container: [
          [{ header: [1, 2, 3, false] }],
          ['bold', 'italic', 'underline', 'strike'],
          ['blockquote', 'code-block'],
          [{ list: 'ordered' }, { list: 'bullet' }],
          ['link', 'image', 'video'],
          ['clean'],
        ],
        handlers: { image: imageHandler },
      },
    }),
    [],
  )

  const addMetaField = () =>
    setCustomMetadata((prev) => [...prev, { key: '', value: '' }])

  const updateMeta = (i: number, field: keyof MetadataField, val: string) =>
    setCustomMetadata((prev) =>
      prev.map((m, idx) => (idx === i ? { ...m, [field]: val } : m)),
    )

  const removeMeta = (i: number) =>
    setCustomMetadata((prev) => prev.filter((_, idx) => idx !== i))

  const save = async () => {
    setError('')
    if (!selectedType.trim()) { setError('Entry type is required'); return }
    if (!journalId && !entryId) { setError('No journal selected'); return }

    setSaving(true)
    try {
      // Ensure type exists
      if (!entryTypes.find((t) => t.name === selectedType)) {
        await entryTypesApi.create(selectedType)
      }

      const payload = {
        type: selectedType,
        name: entryName.trim() || undefined,
        body,
        custom_metadata: customMetadata.filter((m) => m.key.trim()),
      }

      if (entryId) {
        await entriesApi.update(entryId, payload)
        navigate(`/entries/${entryId}`)
      } else {
        const r = await entriesApi.create(journalId, payload)
        navigate(`/entries/${r.data.id}`)
      }
    } catch {
      setError('Failed to save. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  const handleChange: ReactQuillProps['onChange'] = (_html, _delta, _source, editor) => {
    setBody((editor as UnprivilegedEditor).getContents())
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.typeRow}>
          <label className="label">Entry Type</label>
          <input
            className="input"
            list="entry-types-list"
            placeholder="e.g. Reflection, Dream, Travel…"
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value)}
            style={{ maxWidth: 280 }}
          />
          <datalist id="entry-types-list">
            {entryTypes.map((t) => (
              <option key={t.id} value={t.name} />
            ))}
          </datalist>
        </div>

        <div className={styles.typeRow}>
          <label className="label">
            Entry Name{' '}
            <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>(optional)</span>
          </label>
          <input
            className="input"
            placeholder="Leave empty to auto-generate from date"
            value={entryName}
            onChange={(e) => setEntryName(e.target.value)}
            style={{ maxWidth: 320 }}
          />
        </div>

        <details className={styles.metaPanel}>
          <summary className={styles.metaSummary}>
            Custom fields ({customMetadata.length})
          </summary>
          <div className={styles.metaFields}>
            {customMetadata.map((m, i) => (
              <div key={i} className={styles.metaRow}>
                <input
                  className="input"
                  placeholder="Field name"
                  value={m.key}
                  onChange={(e) => updateMeta(i, 'key', e.target.value)}
                  style={{ maxWidth: 160 }}
                />
                <input
                  className="input"
                  placeholder="Value"
                  value={m.value}
                  onChange={(e) => updateMeta(i, 'value', e.target.value)}
                />
                <button
                  className="btn btn-danger"
                  style={{ padding: '0.4rem 0.7rem' }}
                  onClick={() => removeMeta(i)}
                >
                  ×
                </button>
              </div>
            ))}
            <button className="btn btn-ghost" onClick={addMetaField}>
              + Add field
            </button>
          </div>
        </details>
      </div>

      <div className={`paper ${styles.editorWrap}`}>
        <ReactQuill
          ref={quillRef}
          theme="snow"
          modules={modules}
          value={body as Parameters<typeof ReactQuill>[0]['value']}
          onChange={handleChange}
          placeholder="Begin writing…"
          className={styles.editor}
        />
      </div>

      {error && <p className="error-text">{error}</p>}

      <div className={styles.actions}>
        <button className="btn btn-ghost" onClick={() => navigate(-1)}>
          Cancel
        </button>
        <button className="btn" onClick={save} disabled={saving}>
          {saving ? 'Saving…' : 'Save Entry'}
        </button>
      </div>
    </div>
  )
}
