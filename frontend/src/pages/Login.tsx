import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { authApi } from '../services/api'
import { useAuthStore } from '../stores/authStore'
import styles from './Auth.module.css'

type Mode = 'password' | 'hashkey'

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

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
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
        'Login failed'
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
        ) : (
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
        )}

        {error && <p className="error-text">{error}</p>}

        <button className="btn" type="submit" disabled={loading}>
          {loading ? 'Signing in…' : 'Sign In'}
        </button>

        <p className={styles.footer}>
          No account? <Link to="/register">Register</Link>
        </p>
      </form>
    </div>
  )
}
