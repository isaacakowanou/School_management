import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { forgotPassword, resetPassword } from '../api/auth.js'
import ErrorBanner from '../components/ErrorBanner.jsx'
import LanguageSwitcher from '../components/LanguageSwitcher.jsx'

export default function ForgotPasswordPage() {
  const { t } = useTranslation()
  const [step, setStep] = useState(1)
  const [identifier, setIdentifier] = useState('')
  const [otp, setOtp] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [done, setDone] = useState(false)

  async function handleRequestOtp(event) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await forgotPassword(identifier.trim())
      if (identifier.includes('@')) setDone(true)
      else setStep(2)
    } catch (err) {
      setError(err.message || t('forgotPassword.requestError'))
    } finally {
      setSubmitting(false)
    }
  }

  async function handleResetPassword(event) {
    event.preventDefault()
    setError(null)
    if (newPassword.length < 8) {
      setError(t('forgotPassword.passwordTooShort'))
      return
    }
    setSubmitting(true)
    try {
      await resetPassword(identifier.trim(), otp.trim(), newPassword)
      setDone(true)
    } catch (err) {
      setError(err.message || t('forgotPassword.resetError'))
    } finally {
      setSubmitting(false)
    }
  }

  if (done) {
    return (
      <div className="login-wrap">
        <div className="lang-switcher-floating">
          <LanguageSwitcher />
        </div>
        <div className="card login-card">
          <h1 className="login-title">{t('forgotPassword.successTitle')}</h1>
          <p className="muted" style={{ marginBottom: '1.25rem' }}>
            {identifier.includes('@') ? t('forgotPassword.emailSentMessage') : t('forgotPassword.successMessage')}
          </p>
          <Link to="/login" className="btn btn-primary" style={{ display: 'block', textAlign: 'center' }}>
            {t('forgotPassword.backToSignIn')}
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="login-wrap">
      <div className="lang-switcher-floating">
        <LanguageSwitcher />
      </div>
      {step === 1 ? (
        <form className="card login-card" onSubmit={handleRequestOtp}>
          <h1 className="login-title">{t('forgotPassword.title')}</h1>
          <p className="login-sub">{t('forgotPassword.subtitle')}</p>

          {error && <ErrorBanner message={error} />}

          <label className="field">
            <span>{t('forgotPassword.identifierLabel')}</span>
            <input
              type="text"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              autoComplete="off"
              placeholder={t('forgotPassword.identifierPlaceholder')}
              required
              disabled={submitting}
            />
          </label>

          <button type="submit" className="btn btn-primary" disabled={submitting || !identifier.trim()}>
            {submitting ? t('forgotPassword.sending') : t('forgotPassword.sendRecovery')}
          </button>

          <p style={{ textAlign: 'center', marginTop: '0.75rem', fontSize: '0.875rem' }}>
            <Link to="/login" style={{ color: 'var(--color-primary, #2563eb)' }}>
              {t('forgotPassword.backToLogin')}
            </Link>
          </p>
        </form>
      ) : (
        <form className="card login-card" onSubmit={handleResetPassword}>
          <h1 className="login-title">{t('forgotPassword.step2Title')}</h1>
          <p className="login-sub">
            {t('forgotPassword.step2Subtitle', { identifier })}
          </p>

          {error && <ErrorBanner message={error} />}

          <label className="field">
            <span>{t('forgotPassword.otpLabel')}</span>
            <input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={otp}
              onChange={(e) => setOtp(e.target.value)}
              required
              disabled={submitting}
            />
          </label>

          <label className="field">
            <span>{t('forgotPassword.newPasswordLabel')}</span>
            <div className="password-input-wrap">
              <input
                type={showPassword ? 'text' : 'password'}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                autoComplete="new-password"
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

          <button type="submit" className="btn btn-primary" disabled={submitting || !otp.trim() || !newPassword}>
            {submitting ? t('forgotPassword.resetting') : t('forgotPassword.resetButton')}
          </button>

          <p style={{ textAlign: 'center', marginTop: '0.75rem', fontSize: '0.875rem' }}>
            <button
              type="button"
              onClick={() => { setStep(1); setOtp(''); setError(null) }}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-primary, #2563eb)', fontSize: 'inherit', padding: 0 }}
            >
              {t('forgotPassword.tryDifferent')}
            </button>
          </p>
        </form>
      )}
    </div>
  )
}
