import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import styles from './Help.module.css'

export default function Help() {
  const apiBaseUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8128'
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()

    const loadHelp = async () => {
      setLoading(true)
      setError('')
      try {
        const response = await fetch(`${apiBaseUrl}/help`, {
          signal: controller.signal,
          headers: {
            Accept: 'text/markdown, text/plain;q=0.9',
          },
        })

        if (!response.ok) {
          throw new Error('Could not load help content.')
        }

        const markdown = await response.text()
        setContent(markdown)
      } catch (err) {
        if ((err as { name?: string }).name === 'AbortError') return
        setError('Could not load help content right now.')
      } finally {
        setLoading(false)
      }
    }

    void loadHelp()

    return () => controller.abort()
  }, [apiBaseUrl])

  return (
    <div className={styles.page}>
      {loading ? (
        <p className={styles.state}>Loading help...</p>
      ) : error ? (
        <p className={styles.error}>{error}</p>
      ) : (
        <article className={styles.markdown}>
          <ReactMarkdown>{content}</ReactMarkdown>
        </article>
      )}
    </div>
  )
}
