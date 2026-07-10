import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { changePassword } from '../api/auth.js'
import { useAuth } from '../auth/AuthContext.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'

export default function ChangePasswordPage() {
  const { logout, refreshUser, homePath, user } = useAuth()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [newPassword, setNewPassword] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)

    if (newPassword !== confirm) {
      setError(t('changePassword.passwordMismatch'))
      return
    }

    setSubmitting(true)
    try {
      await changePassword(newPassword, user?.must_change_password ? null : currentPassword)
      const me = await refreshUser()
      navigate(homePath ?? '/', { replace: true })
      void me
    } catch (err) {
      if (err.detail?.code === 'current_password_required') {
        setError(t('changePassword.currentPasswordRequired'))
      } else if (err.detail?.code === 'current_password_incorrect') {
        setError(t('changePassword.currentPasswordIncorrect'))
      } else {
        setError(err.message)
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={handleSubmit}>
        <h1 className="login-title">{t('changePassword.title')}</h1>
        <p className="login-sub">{t('changePassword.subtitle')}</p>

        {error && <ErrorBanner message={error} />}

        {!user?.must_change_password && (
          <label className="field">
            <span>{t('changePassword.currentPassword')}</span>
            <input
              type={showPassword ? 'text' : 'password'}
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              autoComplete="current-password"
              required
              disabled={submitting}
            />
          </label>
        )}

        <label className="field">
          <span>{t('changePassword.newPassword')}</span>
          <div className="password-input-wrap">
            <input
              type={showPassword ? 'text' : 'password'}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              autoComplete="new-password"
              minLength={8}
              required
              disabled={submitting}
            />
            <button
              type="button"
              className="password-toggle"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? t('login.hidePassword') : t('login.showPassword')}
              aria-pressed={showPassword}
            >
              {showPassword ? (
                <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                  <path d="M2.25 12s3.5-6.75 9.75-6.75S21.75 12 21.75 12s-3.5 6.75-9.75 6.75S2.25 12 2.25 12Z" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
                  <path d="M12 15.25A3.25 3.25 0 1 0 12 8.75a3.25 3.25 0 0 0 0 6.5Z" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
                  <path d="M4 4l16 16" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                  <path d="M2.25 12s3.5-6.75 9.75-6.75S21.75 12 21.75 12s-3.5 6.75-9.75 6.75S2.25 12 2.25 12Z" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
                  <path d="M12 15.25A3.25 3.25 0 1 0 12 8.75a3.25 3.25 0 0 0 0 6.5Z" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
                </svg>
              )}
            </button>
          </div>
        </label>

        <p className="muted" style={{ fontSize: '0.875rem' }}>
          {t('changePassword.otherSessionsNotice')}
        </p>

        <label className="field">
          <span>{t('changePassword.confirmPassword')}</span>
          <input
            type={showPassword ? 'text' : 'password'}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="new-password"
            minLength={8}
            required
            disabled={submitting}
          />
        </label>

        <button type="submit" className="btn btn-primary" disabled={submitting}>
          {submitting ? t('changePassword.saving') : t('changePassword.submit')}
        </button>

        <button
          type="button"
          className="btn btn-ghost"
          style={{ marginTop: '0.5rem' }}
          onClick={logout}
          disabled={submitting}
        >
          {t('common.logout')}
        </button>
      </form>
    </div>
  )
}
