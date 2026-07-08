import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { createParent } from '../api/parents.js'
import ErrorBanner from '../components/ErrorBanner.jsx'

const EMPTY_FORM = {
  name: '',
  email: '',
  phone: '',
}

export default function AdminParentCreatePage() {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [form, setForm] = useState(EMPTY_FORM)
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [created, setCreated] = useState(null)
  const [copied, setCopied] = useState(false)

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)

    if (!form.name.trim()) {
      setError(t('parents.errorNameRequired'))
      return
    }

    setSaving(true)
    try {
      const data = await createParent(form)
      setCreated({
        name: data.name,
        email: data.email,
        tempPassword: data.temp_password,
        emailSent: data.email_sent,
        smsSent: data.sms_sent,
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  function copyPassword() {
    navigator.clipboard.writeText(created.tempPassword).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  if (created) {
    return (
      <section className="admin-page">
        <div className="card admin-form">
          <h2 className="page-title">{t('parents.accountCreated')}</h2>
          <p className="muted" style={{ marginBottom: '1rem' }}>
            {t('parents.addedMessage', {
              name: created.email ? `${created.name} <${created.email}>` : created.name,
            })}
          </p>

          <div
            className="field"
            style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}
          >
            <code
              style={{
                flex: 1,
                padding: '0.5rem 0.75rem',
                background: 'var(--color-surface-alt, #f5f5f5)',
                borderRadius: '6px',
                fontSize: '1rem',
                letterSpacing: '0.05em',
                wordBreak: 'break-all',
              }}
            >
              {created.tempPassword}
            </code>
            <button type="button" className="btn btn-ghost" onClick={copyPassword}>
              {copied ? t('common.copied') : t('common.copy')}
            </button>
          </div>

          <p className="muted" style={{ marginTop: '0.5rem', fontSize: '0.85rem' }}>
            {t('parents.firstLoginHint')}
          </p>

          {created.emailSent === false && <ErrorBanner message={t('common.notifyEmailFailed')} />}
          {created.smsSent === false && <ErrorBanner message={t('common.notifySmsFailed')} />}

          <div className="grade-actions" style={{ marginTop: '1.5rem' }}>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => {
                setCreated(null)
                setCopied(false)
                setForm(EMPTY_FORM)
              }}
            >
              {t('parents.addAnother')}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => navigate('/admin/parents')}
            >
              {t('common.done')}
            </button>
          </div>
        </div>
      </section>
    )
  }

  return (
    <section className="admin-page">
      <Link to="/admin/parents" className="back-link">
        ← {t('nav.parents')}
      </Link>

      <div className="report-header">
        <div>
          <h2 className="page-title">{t('parents.addParent')}</h2>
          <p className="muted">{t('parents.createSubtitle')}</p>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}

      <form className="card admin-form" onSubmit={handleSubmit}>
        <label className="field">
          <span>{t('common.name')}</span>
          <input
            value={form.name}
            onChange={(event) => updateField('name', event.target.value)}
            disabled={saving}
            required
          />
        </label>

        <label className="field">
          <span>{t('teachers.emailOptional')}</span>
          <input
            type="text"
            value={form.email}
            onChange={(event) => updateField('email', event.target.value)}
            disabled={saving}
          />
        </label>

        <label className="field">
          <span>{t('common.phone')}</span>
          <input
            value={form.phone}
            onChange={(event) => updateField('phone', event.target.value)}
            disabled={saving}
          />
        </label>

        <div className="grade-actions">
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? t('parents.creating') : t('parents.create')}
          </button>
          <Link to="/admin/parents" className="btn btn-ghost">
            {t('common.cancel')}
          </Link>
        </div>
      </form>
    </section>
  )
}
