import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getCurrentParent, updateCurrentParent } from '../api/parents.js'
import { changePassword } from '../api/auth.js'
import { useAuth } from '../auth/AuthContext.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'

export default function ParentSettingsPage() {
  const { refreshUser } = useAuth()

  // Profile section
  const [profileForm, setProfileForm] = useState({ name: '', phone: '' })
  const [profileLoading, setProfileLoading] = useState(true)
  const [profileSaving, setProfileSaving] = useState(false)
  const [profileError, setProfileError] = useState(null)
  const [profileSuccess, setProfileSuccess] = useState(false)

  // Password section
  const [pwForm, setPwForm] = useState({ newPassword: '', confirm: '' })
  const [showPassword, setShowPassword] = useState(false)
  const [pwSaving, setPwSaving] = useState(false)
  const [pwError, setPwError] = useState(null)
  const [pwSuccess, setPwSuccess] = useState(false)

  useEffect(() => {
    getCurrentParent()
      .then((p) => setProfileForm({ name: p.name, phone: p.phone ?? '' }))
      .catch(() => setProfileError('Could not load your profile.'))
      .finally(() => setProfileLoading(false))
  }, [])

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
      setProfileError(err.message || 'Could not save profile.')
    } finally {
      setProfileSaving(false)
    }
  }

  async function handlePasswordSubmit(event) {
    event.preventDefault()
    setPwError(null)
    setPwSuccess(false)

    if (pwForm.newPassword !== pwForm.confirm) {
      setPwError('Passwords do not match.')
      return
    }

    setPwSaving(true)
    try {
      await changePassword(pwForm.newPassword)
      setPwForm({ newPassword: '', confirm: '' })
      setPwSuccess(true)
    } catch (err) {
      setPwError(err.message || 'Could not change password.')
    } finally {
      setPwSaving(false)
    }
  }

  if (profileLoading) {
    return (
      <section className="admin-page">
        <p className="muted">Loading…</p>
      </section>
    )
  }

  return (
    <section className="admin-page">
      <Link to="/" className="back-link">&larr; Back</Link>
      <div className="report-header">
        <div>
          <h2 className="page-title">Settings</h2>
          <p className="muted">Update your name, phone, or password.</p>
        </div>
      </div>

      {/* Profile */}
      <div className="card admin-form" style={{ marginBottom: '1.5rem' }}>
        <h3 style={{ marginTop: 0, marginBottom: '1rem' }}>Profile</h3>

        {profileError && <ErrorBanner message={profileError} />}
        {profileSuccess && (
          <p style={{ color: 'var(--color-success, #166534)', marginBottom: '0.75rem' }}>
            Profile updated.
          </p>
        )}

        <form onSubmit={handleProfileSubmit}>
          <label className="field">
            <span>Name</span>
            <input
              value={profileForm.name}
              onChange={(e) => setProfileForm((f) => ({ ...f, name: e.target.value }))}
              disabled={profileSaving}
              required
            />
          </label>

          <label className="field">
            <span>Phone</span>
            <input
              value={profileForm.phone}
              onChange={(e) => setProfileForm((f) => ({ ...f, phone: e.target.value }))}
              disabled={profileSaving}
              type="tel"
            />
          </label>

          <div className="grade-actions">
            <button type="submit" className="btn btn-primary" disabled={profileSaving}>
              {profileSaving ? 'Saving…' : 'Save changes'}
            </button>
          </div>
        </form>
      </div>

      {/* Change password */}
      <div className="card admin-form">
        <h3 style={{ marginTop: 0, marginBottom: '1rem' }}>Change password</h3>

        {pwError && <ErrorBanner message={pwError} />}
        {pwSuccess && (
          <p style={{ color: 'var(--color-success, #166534)', marginBottom: '0.75rem' }}>
            Password changed successfully.
          </p>
        )}

        <form onSubmit={handlePasswordSubmit}>
          <label className="field">
            <span>New password</span>
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
                aria-label={showPassword ? 'Hide password' : 'Show password'}
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

          <label className="field">
            <span>Confirm password</span>
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
              {pwSaving ? 'Saving…' : 'Change password'}
            </button>
          </div>
        </form>
      </div>
    </section>
  )
}
