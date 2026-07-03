import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { createParent } from '../api/parents.js'
import ErrorBanner from '../components/ErrorBanner.jsx'

const EMPTY_FORM = {
  name: '',
  email: '',
  phone: '',
}

export default function AdminParentCreatePage() {
  const navigate = useNavigate()
  const [form, setForm] = useState(EMPTY_FORM)
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [created, setCreated] = useState(null) // { name, email, tempPassword }
  const [copied, setCopied] = useState(false)

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)

    if (!form.name.trim() || !form.email.trim()) {
      setError('Name and email are required.')
      return
    }

    setSaving(true)
    try {
      const data = await createParent(form)
      setCreated({ name: data.name, email: data.email, tempPassword: data.temp_password })
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
          <h2 className="page-title">Parent account created</h2>
          <p className="muted" style={{ marginBottom: '1rem' }}>
            {created.name} &lt;{created.email}&gt; has been added. A temporary password was generated below.
            Share it with the parent — <strong>it will not be shown again</strong>.
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
              {copied ? 'Copied!' : 'Copy'}
            </button>
          </div>

          <p className="muted" style={{ marginTop: '0.5rem', fontSize: '0.85rem' }}>
            The parent will be required to change this password on first login.
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
              Add another parent
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => navigate('/admin/parents')}
            >
              Done
            </button>
          </div>
        </div>
      </section>
    )
  }

  return (
    <section className="admin-page">
      <Link to="/admin/parents" className="back-link">
        &lt;- Parents
      </Link>

      <div className="report-header">
        <div>
          <h2 className="page-title">Add parent</h2>
          <p className="muted">A temporary password will be generated and emailed to the parent.</p>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}

      <form className="card admin-form" onSubmit={handleSubmit}>
        <label className="field">
          <span>Name</span>
          <input
            value={form.name}
            onChange={(event) => updateField('name', event.target.value)}
            disabled={saving}
            required
          />
        </label>

        <label className="field">
          <span>Email</span>
          <input
            type="email"
            value={form.email}
            onChange={(event) => updateField('email', event.target.value)}
            disabled={saving}
            required
          />
        </label>

        <label className="field">
          <span>Phone</span>
          <input
            value={form.phone}
            onChange={(event) => updateField('phone', event.target.value)}
            disabled={saving}
          />
        </label>

        <div className="grade-actions">
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? 'Creating...' : 'Create parent'}
          </button>
          <Link to="/admin/parents" className="btn btn-ghost">
            Cancel
          </Link>
        </div>
      </form>
    </section>
  )
}
