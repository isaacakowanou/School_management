import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { resetPasswordByEmail } from '../api/auth.js'
import ErrorBanner from '../components/ErrorBanner.jsx'
import LanguageSwitcher from '../components/LanguageSwitcher.jsx'

export default function EmailResetPasswordPage() {
  const { t } = useTranslation()
  const [params] = useSearchParams()
  const [form, setForm] = useState({ password: '', confirm: '' })
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [done, setDone] = useState(false)

  async function submit(event) {
    event.preventDefault()
    if (form.password !== form.confirm) {
      setError(t('changePassword.passwordMismatch'))
      return
    }
    setSaving(true)
    setError(null)
    try {
      await resetPasswordByEmail(params.get('token') || '', form.password)
      setDone(true)
    } catch (err) {
      setError(t('forgotPassword.invalidResetLink'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="login-wrap">
      <div className="lang-switcher-floating"><LanguageSwitcher /></div>
      <form className="card login-card" onSubmit={submit}>
        <h1 className="login-title">{t('forgotPassword.emailResetTitle')}</h1>
        {done ? (
          <><p className="login-sub">{t('forgotPassword.emailResetDone')}</p><Link className="btn btn-primary" to="/login">{t('forgotPassword.backToSignIn')}</Link></>
        ) : (
          <>
            <p className="login-sub">{t('forgotPassword.emailResetSubtitle')}</p>
            {error && <ErrorBanner message={error} />}
            <label className="field"><span>{t('changePassword.newPassword')}</span><input type="password" minLength={8} autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required /></label>
            <label className="field"><span>{t('changePassword.confirmPassword')}</span><input type="password" minLength={8} autoComplete="new-password" value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} required /></label>
            <button className="btn btn-primary" disabled={saving || !params.get('token')}>{saving ? t('common.saving') : t('forgotPassword.resetButton')}</button>
          </>
        )}
      </form>
    </div>
  )
}
