import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { getCurrentParent, updateCurrentParent } from '../api/parents.js'
import { changePassword } from '../api/auth.js'
import { useAuth } from '../auth/AuthContext.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'

export default function ParentSettingsPage() {
  const { refreshUser } = useAuth()
  const { t } = useTranslation()

  const [profileForm, setProfileForm] = useState({ name: '', phone: '' })
  const [profileLoading, setProfileLoading] = useState(true)
  const [profileSaving, setProfileSaving] = useState(false)
  const [profileError, setProfileError] = useState(null)
  const [profileSuccess, setProfileSuccess] = useState(false)

  const [pwForm, setPwForm] = useState({ currentPassword: '', newPassword: '', confirm: '' })
  const [showPassword, setShowPassword] = useState(false)
  const [pwSaving, setPwSaving] = useState(false)
  const [pwError, setPwError] = useState(null)
  const [pwSuccess, setPwSuccess] = useState(false)

  useEffect(() => {
    getCurrentParent()
      .then((p) => setProfileForm({ name: p.name, phone: p.phone ?? '' }))
      .catch(() => setProfileError(t('settings.profileLoadError')))
      .finally(() => setProfileLoading(false))
  }, [t])

  async function handleProfileSubmit(event) {
    event.preventDefault()
    setProfileError(null)
    setProfileSuccess(false)
    setProfileSaving(true)
    try {
      const updated = await updateCurrentParent({
        name: profileForm.name,
        phone: profileForm.phone,
      })
      setProfileForm({ name: updated.name, phone: updated.phone ?? '' })
      await refreshUser()
      setProfileSuccess(true)
    } catch (err) {
      setProfileError(err.message || t('settings.profileSaveError'))
    } finally {
      setProfileSaving(false)
    }
  }

  async function handlePasswordSubmit(event) {
    event.preventDefault()
    setPwError(null)
    setPwSuccess(false)

    if (pwForm.newPassword !== pwForm.confirm) {
      setPwError(t('changePassword.passwordMismatch'))
      return
    }

    setPwSaving(true)
    try {
      await changePassword(pwForm.newPassword, pwForm.currentPassword)
      setPwForm({ currentPassword: '', newPassword: '', confirm: '' })
      setPwSuccess(true)
    } catch (err) {
      if (err.detail?.code === 'current_password_required') {
        setPwError(t('changePassword.currentPasswordRequired'))
      } else if (err.detail?.code === 'current_password_incorrect') {
        setPwError(t('changePassword.currentPasswordIncorrect'))
      } else {
        setPwError(err.message || t('settings.passwordError'))
      }
    } finally {
      setPwSaving(false)
    }
  }

  if (profileLoading) {
    return (
      <section className="parent-page">
        <p className="muted">{t('common.loading')}</p>
      </section>
    )
  }

  return (
    <section className="parent-page parent-settings-page">
      <Link to="/" className="back-link">← {t('common.back')}</Link>
      <div className="report-header">
        <div>
          <h2 className="page-title">{t('common.settings')}</h2>
          <p className="muted">{t('settings.subtitle')}</p>
        </div>
      </div>

      <div className="card admin-form parent-settings-card">
        <h3 className="card-title">{t('settings.profileTitle')}</h3>

        {profileError && <ErrorBanner message={profileError} />}
        {profileSuccess && (
          <p style={{ color: 'var(--color-success, #166534)', marginBottom: '0.75rem' }}>
            {t('settings.profileUpdated')}
          </p>
        )}

        <form onSubmit={handleProfileSubmit}>
          <label className="field">
            <span>{t('common.name')}</span>
            <input
              value={profileForm.name}
              onChange={(e) => setProfileForm((f) => ({ ...f, name: e.target.value }))}
              disabled={profileSaving}
              required
            />
          </label>

          <label className="field">
            <span>{t('common.phone')}</span>
            <input
              value={profileForm.phone}
              onChange={(e) => setProfileForm((f) => ({ ...f, phone: e.target.value }))}
              disabled={profileSaving}
              type="tel"
            />
          </label>

          <div className="grade-actions">
            <button type="submit" className="btn btn-primary" disabled={profileSaving}>
              {profileSaving ? t('common.saving') : t('common.saveChanges')}
            </button>
          </div>
        </form>
      </div>

      <div className="card admin-form parent-settings-card">
        <h3 className="card-title">{t('settings.changePasswordTitle')}</h3>

        {pwError && <ErrorBanner message={pwError} />}
        {pwSuccess && (
          <p style={{ color: 'var(--color-success, #166534)', marginBottom: '0.75rem' }}>
            {t('settings.passwordChanged')}
          </p>
        )}

        <form onSubmit={handlePasswordSubmit}>
          <label className="field">
            <span>{t('changePassword.currentPassword')}</span>
            <input
              type={showPassword ? 'text' : 'password'}
              value={pwForm.currentPassword}
              onChange={(e) => setPwForm((f) => ({ ...f, currentPassword: e.target.value }))}
              autoComplete="current-password"
              required
              disabled={pwSaving}
            />
          </label>

          <label className="field">
            <span>{t('changePassword.newPassword')}</span>
            <div className="password-input-wrap">
              <input
                type={showPassword ? 'text' : 'password'}
                value={pwForm.newPassword}
                onChange={(e) => setPwForm((f) => ({ ...f, newPassword: e.target.value }))}
                autoComplete="new-password"
                minLength={8}
                required
                disabled={pwSaving}
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
              value={pwForm.confirm}
              onChange={(e) => setPwForm((f) => ({ ...f, confirm: e.target.value }))}
              autoComplete="new-password"
              minLength={8}
              required
              disabled={pwSaving}
            />
          </label>

          <div className="grade-actions">
            <button type="submit" className="btn btn-primary" disabled={pwSaving}>
              {pwSaving ? t('common.saving') : t('settings.changePasswordTitle')}
            </button>
          </div>
        </form>
      </div>
    </section>
  )
}
