import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { createTeacher } from '../api/teachers.js'
import ErrorBanner from '../components/ErrorBanner.jsx'

const EMPTY_FORM = {
  name: '',
  email: '',
  phone: '',
  employeeNumber: '',
}

export default function AdminTeacherCreatePage() {
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
      setError(t('teachers.errorNameRequired'))
      return
    }

    setSaving(true)
    try {
      const data = await createTeacher(form)
      setCreated({ name: data.name, email: data.email, employeeNumber: data.employee_number, tempPassword: data.temp_password })
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
          <h2 className="page-title">{t('teachers.accountCreated')}</h2>
          <p className="muted" style={{ marginBottom: '1rem' }}>
            {t('teachers.addedMessage', {
              name: created.email ? `${created.name} <${created.email}>` : created.name,
              number: created.employeeNumber,
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
            {t('teachers.firstLoginHint')}
          </p>

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
              {t('teachers.addAnother')}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => navigate('/admin/teachers')}
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
      <Link to="/admin/teachers" className="back-link">
        ← {t('nav.teachers')}
      </Link>

      <div className="report-header">
        <div>
          <h2 className="page-title">{t('teachers.addTeacher')}</h2>
          <p className="muted">{t('teachers.createSubtitle')}</p>
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
          <span>{t('teachers.phoneOptional')}</span>
          <input
            type="text"
            value={form.phone}
            onChange={(event) => updateField('phone', event.target.value)}
            disabled={saving}
            placeholder="+22961000000"
          />
        </label>

        <label className="field">
          <span>{t('teachers.employeeNumber')}</span>
          <input
            value={form.employeeNumber}
            onChange={(event) => updateField('employeeNumber', event.target.value)}
            disabled={saving}
            placeholder={t('students.autoGenerated')}
          />
        </label>

        <div className="grade-actions">
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? t('teachers.creating') : t('teachers.create')}
          </button>
          <Link to="/admin/teachers" className="btn btn-ghost">
            {t('common.cancel')}
          </Link>
        </div>
      </form>
    </section>
  )
}
