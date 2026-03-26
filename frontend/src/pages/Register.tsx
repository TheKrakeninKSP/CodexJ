import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { authApi } from '../services/api'
import { useAuthStore } from '../stores/authStore'
import styles from './Auth.module.css'

function parseJwt(token: string): { username?: string; is_privileged?: boolean } {
  try {
    return JSON.parse(atob(token.split('.')[1]))
  } catch {
    return {}
  }
}

export default function Register() {
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [hashkey, setHashkey] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await authApi.register(username, password)
      const { access_token, hashkey: hk } = res.data
      const payload = parseJwt(access_token)
      setAuth(access_token, payload.username ?? username, Boolean(payload.is_privileged))
      setHashkey(hk)
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Registration failed'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  if (hashkey) {
    return (
      <div className={styles.page}>
        <div className={`paper ${styles.card}`}>
          <h2 className={styles.title}>Save your Hashkey</h2>
          <p className={styles.subtitle}>
            This is shown <strong>once</strong>. Store it securely as it is the only way
            to recover your account if you forget your password.
          </p>
          <div className={styles.hashkeyBox}>{hashkey}</div>
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
        <h1 className={styles.title}>Create Account</h1>
        <p className={styles.subtitle}>CodexJ</p>

        <div className={styles.field}>
          <label className="label">Username</label>
          <input
            className="input"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            minLength={3}
            required
            autoFocus
          />
        </div>

        <div className={styles.field}>
          <label className="label">Password</label>
          <input
            className="input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            required
          />
        </div>

        {error && <p className="error-text">{error}</p>}

        <button className="btn" type="submit" disabled={loading}>
          {loading ? 'Creating…' : 'Create Account'}
        </button>

        <p className={styles.footer}>
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </form>
    </div>
  )
}
