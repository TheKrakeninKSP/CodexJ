import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { authApi } from '../services/api'
import { useAuthStore } from '../stores/authStore'
import styles from './Auth.module.css'

type Mode = 'password' | 'hashkey' | 'import'

function parseJwt(token: string): { username?: string; is_privileged?: boolean } {
  try {
    return JSON.parse(atob(token.split('.')[1]))
  } catch {
    return {}
  }
}

export default function Login() {
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [mode, setMode] = useState<Mode>('password')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [hashkey, setHashkey] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  // Import mode state
  const [importFile, setImportFile] = useState<File | null>(null)
  const [encryptionKey, setEncryptionKey] = useState('')

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      if (mode === 'import') {
        // Import mode: recreate account directly from dump credentials
        if (!importFile) {
          setError('Please select a dump file')
          setLoading(false)
          return
        }
        if (!encryptionKey) {
          setError('Please enter your hashkey')
          setLoading(false)
          return
        }
        const res = await authApi.registerWithImport(encryptionKey, importFile)
        const token = res.data.access_token
        const payload = parseJwt(token)
        setAuth(token, payload.username ?? res.data.username, Boolean(payload.is_privileged))
        navigate('/')
        return
      }

      // Normal login/unlock flow
      const res =
        mode === 'password'
          ? await authApi.login(username, password)
          : await authApi.unlock(username, hashkey)
      const token = res.data.access_token
      const payload = parseJwt(token)
      setAuth(token, payload.username ?? username, Boolean(payload.is_privileged))
      navigate('/')
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Operation failed'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.page}>
      <form className={`paper ${styles.card}`} onSubmit={submit}>
        <h1 className={styles.title}>CodexJ</h1>

        <div className={styles.modeTabs}>
          <button
            type="button"
            className={`${styles.tab} ${mode === 'password' ? styles.activeTab : ''}`}
            onClick={() => setMode('password')}
          >
            Password
          </button>
          <button
            type="button"
            className={`${styles.tab} ${mode === 'hashkey' ? styles.activeTab : ''}`}
            onClick={() => setMode('hashkey')}
          >
            Hashkey
          </button>
          <button
            type="button"
            className={`${styles.tab} ${mode === 'import' ? styles.activeTab : ''}`}
            onClick={() => setMode('import')}
          >
            Import
          </button>
        </div>

        {mode !== 'import' && (
          <div className={styles.field}>
            <label className="label">Username</label>
            <input
              className="input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
            />
          </div>
        )}

        {mode === 'password' ? (
          <div className={styles.field}>
            <label className="label">Password</label>
            <input
              className="input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
        ) : mode === 'hashkey' ? (
          <div className={styles.field}>
            <label className="label">Hashkey</label>
            <input
              className="input"
              value={hashkey}
              onChange={(e) => setHashkey(e.target.value)}
              required
              placeholder="64-character hex key"
            />
          </div>
        ) : (
          <>
            <div className={styles.field}>
              <label className="label">Hashkey</label>
              <input
                className="input"
                value={encryptionKey}
                onChange={(e) => setEncryptionKey(e.target.value)}
                required
                placeholder="64-character hex key shown at registration"
              />
            </div>
            <div className={styles.field}>
              <label className="label">Dump File</label>
              <input
                type="file"
                accept=".bin"
                onChange={(e) => setImportFile(e.target.files?.[0] ?? null)}
                required
              />
            </div>
          </>
        )}

        {error && <p className="error-text">{error}</p>}

        <button className="btn" type="submit" disabled={loading}>
          {loading
            ? mode === 'import'
              ? 'Importing...'
              : 'Signing in...'
            : mode === 'import'
              ? 'Import & Create Account'
              : 'Sign In'}
        </button>

        <p className={styles.footer}>
          No account? <Link to="/register">Register</Link>
        </p>
      </form>
    </div>
  )
}
