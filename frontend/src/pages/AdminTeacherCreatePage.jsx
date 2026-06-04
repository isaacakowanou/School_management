import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { createTeacher } from '../api/teachers.js'
import ErrorBanner from '../components/ErrorBanner.jsx'

const EMPTY_FORM = {
  name: '',
  email: '',
  password: '',
  employeeNumber: '',
}

export default function AdminTeacherCreatePage() {
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

    if (!form.name.trim() || !form.email.trim() || !form.password.trim() || !form.employeeNumber.trim()) {
      setError('Name, email, password, and employee number are required.')
      return
    }

    setSaving(true)
    try {
      await createTeacher(form)
      navigate('/admin/teachers', {
        state: { message: 'Teacher created.' },
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="admin-page">
      <Link to="/admin/teachers" className="back-link">
        &lt;- Teachers
      </Link>

      <div className="report-header">
        <div>
          <h2 className="page-title">Add teacher</h2>
          <p className="muted">Create a teacher account for course access.</p>
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
          <span>Employee number</span>
          <input
            value={form.employeeNumber}
            onChange={(event) => updateField('employeeNumber', event.target.value)}
            disabled={saving}
            required
          />
        </label>

        <div className="grade-actions">
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? 'Creating...' : 'Create teacher'}
          </button>
          <Link to="/admin/teachers" className="btn btn-ghost">
            Cancel
          </Link>
        </div>
      </form>
    </section>
  )
}
