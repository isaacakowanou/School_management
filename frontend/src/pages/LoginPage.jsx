import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import { homePathForRole, isPathForRole } from '../utils/roles.js'

export default function LoginPage() {
  const { login, isAuthenticated, bootstrapping, role, homePath } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const from = location.state?.from?.pathname

  // Already signed in -> go to the right area (restore `from` only if it fits the role).
  if (!bootstrapping && isAuthenticated) {
    const dest = from && isPathForRole(from, role) ? from : homePath
    return <Navigate to={dest} replace />
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const me = await login(email.trim(), password)
      const dest = from && isPathForRole(from, me.role) ? from : homePathForRole(me.role)
      navigate(dest, { replace: true })
    } catch (err) {
      setError(err.message || 'Sign in failed. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={handleSubmit}>
        <h1 className="login-title">School Reports</h1>
        <p className="login-sub">Sign in to your account</p>

        {error && <ErrorBanner message={error} />}

        <label className="field">
          <span>Email</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="username"
            required
          />
        </label>

        <label className="field">
          <span>Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>

        <button type="submit" className="btn btn-primary" disabled={submitting}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
