import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { authApi } from '../services/api'
import { useAuthStore } from '../stores/authStore'
import styles from './Auth.module.css'

type Mode = 'password' | 'hashkey' | 'import'

function parseJwt(token: string): { username?: string } {
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
  const [newPassword, setNewPassword] = useState('')
  const [showHashkey, setShowHashkey] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      if (mode === 'import') {
        // Import mode: register new user with imported data
        if (!importFile) {
          setError('Please select a dump file')
          setLoading(false)
          return
        }
        if (!encryptionKey || encryptionKey.length < 8) {
          setError('Encryption key must be at least 8 characters')
          setLoading(false)
          return
        }
        if (!newPassword || newPassword.length < 8) {
          setError('Password must be at least 8 characters')
          setLoading(false)
          return
        }
        if (!username || username.length < 3) {
          setError('Username must be at least 3 characters')
          setLoading(false)
          return
        }

        const res = await authApi.registerWithImport(
          username,
          newPassword,
          encryptionKey,
          importFile,
        )
        const token = res.data.access_token
        const payload = parseJwt(token)
        setAuth(token, payload.username ?? username)
        setShowHashkey(res.data.hashkey)
        setLoading(false)
        return
      }

      // Normal login/unlock flow
      const res =
        mode === 'password'
          ? await authApi.login(username, password)
          : await authApi.unlock(username, hashkey)
      const token = res.data.access_token
      const payload = parseJwt(token)
      setAuth(token, payload.username ?? username)
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

  // Show hashkey screen after successful import
  if (showHashkey) {
    return (
      <div className={styles.page}>
        <div className={`paper ${styles.card}`}>
          <h2 className={styles.title}>Save Your Hashkey</h2>
          <p className={styles.subtitle}>
            This is shown <strong>once</strong>. Store it securely as it is the only way
            to recover your account if you forget your password.
          </p>
          <div className={styles.hashkeyBox}>{showHashkey}</div>
          <button
            className="btn"
            style={{ marginTop: '1.5rem', width: '100%' }}
            onClick={() => navigate('/')}
          >
            I've saved it. Continue.
          </button>
        </div>
      </div>
    )
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
              <label className="label">New Password</label>
              <input
                className="input"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                minLength={8}
                placeholder="Min 8 characters"
              />
            </div>
            <div className={styles.field}>
              <label className="label">Encryption Key</label>
              <input
                className="input"
                type="password"
                value={encryptionKey}
                onChange={(e) => setEncryptionKey(e.target.value)}
                required
                placeholder="Key used to encrypt the dump"
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
