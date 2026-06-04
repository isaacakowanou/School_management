import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { createParent } from '../api/parents.js'
import ErrorBanner from '../components/ErrorBanner.jsx'

const EMPTY_FORM = {
  name: '',
  email: '',
  password: '',
  phone: '',
}

export default function AdminParentCreatePage() {
  const navigate = useNavigate()
  const [form, setForm] = useState(EMPTY_FORM)
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)

    if (!form.name.trim() || !form.email.trim() || !form.password.trim()) {
      setError('Name, email, and password are required.')
      return
    }

    setSaving(true)
    try {
      await createParent(form)
      navigate('/admin/parents', {
        state: { message: 'Parent created.' },
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="admin-page">
      <Link to="/admin/parents" className="back-link">
        &lt;- Parents
      </Link>

      <div className="report-header">
        <div>
          <h2 className="page-title">Add parent</h2>
          <p className="muted">Create a parent account for portal access.</p>
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
          <span>Password</span>
          <input
            type="password"
            value={form.password}
            onChange={(event) => updateField('password', event.target.value)}
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
