import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { createStudent } from '../api/students.js'
import ErrorBanner from '../components/ErrorBanner.jsx'

const EMPTY_FORM = {
  firstName: '',
  lastName: '',
  studentNumber: '',
  gradeLevel: '',
}

export default function AdminStudentCreatePage() {
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

    if (!form.firstName.trim() || !form.lastName.trim() || !form.studentNumber.trim() || !form.gradeLevel.trim()) {
      setError('All fields are required.')
      return
    }

    setSaving(true)
    try {
      await createStudent(form)
      navigate('/admin/students', {
        state: { message: 'Student created.' },
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="admin-page">
      <Link to="/admin/students" className="back-link">
        &lt;- Students
      </Link>

      <div className="report-header">
        <div>
          <h2 className="page-title">Add student</h2>
          <p className="muted">Create a student profile for grades and report cards.</p>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}

      <form className="card admin-form" onSubmit={handleSubmit}>
        <label className="field">
          <span>First name</span>
          <input
            value={form.firstName}
            onChange={(event) => updateField('firstName', event.target.value)}
            disabled={saving}
            required
          />
        </label>

        <label className="field">
          <span>Last name</span>
          <input
            value={form.lastName}
            onChange={(event) => updateField('lastName', event.target.value)}
            disabled={saving}
            required
          />
        </label>

        <label className="field">
          <span>Student number</span>
          <input
            value={form.studentNumber}
            onChange={(event) => updateField('studentNumber', event.target.value)}
            disabled={saving}
            required
          />
        </label>

        <label className="field">
          <span>Grade level</span>
          <input
            value={form.gradeLevel}
            onChange={(event) => updateField('gradeLevel', event.target.value)}
            disabled={saving}
            required
          />
        </label>

        <div className="grade-actions">
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? 'Creating...' : 'Create student'}
          </button>
          <Link to="/admin/students" className="btn btn-ghost">
            Cancel
          </Link>
        </div>
      </form>
    </section>
  )
}
