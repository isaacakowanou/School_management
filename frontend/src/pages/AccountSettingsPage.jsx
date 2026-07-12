// Shared parent/teacher/admin settings flow. Role controls only the shell and
// editable profile fields (admins have no phone profile); password changes use
// the same current-password API, whose fresh JWT replaces this device's token
// while the backend invalidates every other session.
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { changePassword, getProfile, updateProfile } from '../api/auth.js'
import { useAuth } from '../auth/AuthContext.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'

export default function AccountSettingsPage() {
  const { role, homePath, refreshUser } = useAuth()
  const { t } = useTranslation()
  const [profile, setProfile] = useState({ name: '', phone: '' })
  const [loading, setLoading] = useState(true)
  const [profileState, setProfileState] = useState({ saving: false, error: null, saved: false })
  const [passwords, setPasswords] = useState({ current: '', next: '', confirm: '' })
  const [passwordState, setPasswordState] = useState({ saving: false, error: null, saved: false })

  useEffect(() => {
    getProfile()
      .then((data) => setProfile({ name: data.name, phone: data.phone || '' }))
      .catch((error) => setProfileState((state) => ({ ...state, error: error.message })))
      .finally(() => setLoading(false))
  }, [])

  async function saveProfile(event) {
    event.preventDefault()
    setProfileState({ saving: true, error: null, saved: false })
    try {
      await updateProfile(profile)
      await refreshUser()
      setProfileState({ saving: false, error: null, saved: true })
    } catch (error) {
      setProfileState({ saving: false, error: error.message, saved: false })
    }
  }

  async function savePassword(event) {
    event.preventDefault()
    if (passwords.next !== passwords.confirm) {
      setPasswordState({ saving: false, error: t('changePassword.passwordMismatch'), saved: false })
      return
    }
    setPasswordState({ saving: true, error: null, saved: false })
    try {
      await changePassword(passwords.next, passwords.current)
      setPasswords({ current: '', next: '', confirm: '' })
      setPasswordState({ saving: false, error: null, saved: true })
    } catch (error) {
      const key = error.detail?.code === 'current_password_incorrect'
        ? 'changePassword.currentPasswordIncorrect'
        : error.detail?.code === 'current_password_required'
          ? 'changePassword.currentPasswordRequired'
          : null
      setPasswordState({ saving: false, error: key ? t(key) : error.message, saved: false })
    }
  }

  if (loading) return <section className={role === 'admin' ? 'admin-page' : 'parent-page'}><p className="muted">{t('common.loading')}</p></section>

  return (
    <section className={`${role === 'admin' ? 'admin-page' : 'parent-page'} parent-settings-page`}>
      <Link to={homePath} className="back-link">← {t('common.back')}</Link>
      <div className="report-header"><div><h2 className="page-title">{t('common.settings')}</h2><p className="muted">{t('settings.subtitle')}</p></div></div>

      <form className="card admin-form parent-settings-card" onSubmit={saveProfile}>
        <h3 className="card-title">{t('settings.profileTitle')}</h3>
        {profileState.error && <ErrorBanner message={profileState.error} />}
        {profileState.saved && <p className="grade-summary">{t('settings.profileUpdated')}</p>}
        <label className="field"><span>{t('common.name')}</span><input value={profile.name} onChange={(e) => setProfile({ ...profile, name: e.target.value })} required /></label>
        {role !== 'admin' && <label className="field"><span>{t('common.phone')}</span><input type="tel" value={profile.phone} onChange={(e) => setProfile({ ...profile, phone: e.target.value })} /></label>}
        <div className="grade-actions"><button className="btn btn-primary" disabled={profileState.saving}>{profileState.saving ? t('common.saving') : t('common.saveChanges')}</button></div>
      </form>

      <form className="card admin-form parent-settings-card" onSubmit={savePassword}>
        <h3 className="card-title">{t('settings.changePasswordTitle')}</h3>
        {passwordState.error && <ErrorBanner message={passwordState.error} />}
        {passwordState.saved && <p className="grade-summary">{t('settings.passwordChanged')}</p>}
        <label className="field"><span>{t('changePassword.currentPassword')}</span><input type="password" autoComplete="current-password" value={passwords.current} onChange={(e) => setPasswords({ ...passwords, current: e.target.value })} required /></label>
        <label className="field"><span>{t('changePassword.newPassword')}</span><input type="password" minLength={8} autoComplete="new-password" value={passwords.next} onChange={(e) => setPasswords({ ...passwords, next: e.target.value })} required /></label>
        <label className="field"><span>{t('changePassword.confirmPassword')}</span><input type="password" minLength={8} autoComplete="new-password" value={passwords.confirm} onChange={(e) => setPasswords({ ...passwords, confirm: e.target.value })} required /></label>
        <p className="muted">{t('changePassword.otherSessionsNotice')}</p>
        <div className="grade-actions"><button className="btn btn-primary" disabled={passwordState.saving}>{passwordState.saving ? t('common.saving') : t('settings.changePasswordTitle')}</button></div>
      </form>
    </section>
  )
}
