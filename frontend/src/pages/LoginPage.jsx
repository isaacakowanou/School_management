import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../auth/AuthContext.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import LanguageSwitcher from '../components/LanguageSwitcher.jsx'
import { homePathForRole, isPathForRole } from '../utils/roles.js'

function isBackendWakeupError(error) {
  return error?.status === 504 || error?.status === 0
}

export default function LoginPage() {
  const { login, isAuthenticated, bootstrapping, role, homePath } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const { t } = useTranslation()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const from = location.state?.from?.pathname
  const passwordToggleLabel = showPassword ? t('login.hidePassword') : t('login.showPassword')

  if (!bootstrapping && isAuthenticated) {
    const dest = from && isPathForRole(from, role) ? from : homePath
    return <Navigate to={dest} replace />
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const me = await login(identifier.trim(), password)
      if (me.must_change_password) {
        navigate('/change-password', { replace: true })
        return
      }
      const dest = from && isPathForRole(from, me.role) ? from : homePathForRole(me.role)
      navigate(dest, { replace: true })
    } catch (err) {
      setError(isBackendWakeupError(err) ? t('login.backendWakeup') : err.message || t('login.submit'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login-wrap">
      <div className="lang-switcher-floating">
        <LanguageSwitcher />
      </div>
      <form className="card login-card" onSubmit={handleSubmit}>
        <h1 className="login-title">{t('login.title')}</h1>
        <p className="login-sub">{t('login.subtitle')}</p>

        {error && <ErrorBanner message={error} />}

        <label className="field">
          <span>{t('login.identifier')}</span>
          <input
            type="text"
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
            autoComplete="username"
            placeholder={t('login.identifierPlaceholder')}
            required
          />
        </label>

        <label className="field">
          <span>{t('login.password')}</span>
          <div className="password-input-wrap">
            <input
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
            <button
              type="button"
              className="password-toggle"
              onClick={() => setShowPassword((current) => !current)}
              aria-label={passwordToggleLabel}
              aria-pressed={showPassword}
              title={passwordToggleLabel}
            >
              {showPassword ? (
                <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                  <path
                    d="M2.25 12s3.5-6.75 9.75-6.75S21.75 12 21.75 12s-3.5 6.75-9.75 6.75S2.25 12 2.25 12Z"
                    fill="none"
                    stroke="currentColor"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="1.8"
                  />
                  <path
                    d="M12 15.25A3.25 3.25 0 1 0 12 8.75a3.25 3.25 0 0 0 0 6.5Z"
                    fill="none"
                    stroke="currentColor"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="1.8"
                  />
                  <path
                    d="M4 4l16 16"
                    fill="none"
                    stroke="currentColor"
                    strokeLinecap="round"
                    strokeWidth="1.8"
                  />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                  <path
                    d="M2.25 12s3.5-6.75 9.75-6.75S21.75 12 21.75 12s-3.5 6.75-9.75 6.75S2.25 12 2.25 12Z"
                    fill="none"
                    stroke="currentColor"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="1.8"
                  />
                  <path
                    d="M12 15.25A3.25 3.25 0 1 0 12 8.75a3.25 3.25 0 0 0 0 6.5Z"
                    fill="none"
                    stroke="currentColor"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="1.8"
                  />
                </svg>
              )}
            </button>
          </div>
        </label>

        <button type="submit" className="btn btn-primary" disabled={submitting}>
          {submitting ? t('login.submitting') : t('login.submit')}
        </button>

        <p className="login-help">
          <Link to="/forgot-password">
            {t('login.forgotPassword')}
          </Link>
        </p>
      </form>
    </div>
  )
}
