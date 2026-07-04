import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { createStudent } from '../api/students.js'
import { listClasses } from '../api/classes.js'
import { SCHOOL_LEVELS } from '../constants/schoolLevels.js'
import ClassSelect from '../components/ClassSelect.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'

const EMPTY_FORM = {
  firstName: '',
  lastName: '',
  studentNumber: '',
  schoolLevel: '',
  classId: '',
  educmasterNumber: '',
}

export default function AdminStudentCreatePage() {
  const navigate = useNavigate()
  const [form, setForm] = useState(EMPTY_FORM)
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [classes, setClasses] = useState([])

  useEffect(() => {
    let cancelled = false
    listClasses()
      .then((data) => {
        if (!cancelled) setClasses(data)
      })
      .catch(() => {
        /* non-fatal: the class dropdown just stays empty */
      })
    return () => {
      cancelled = true
    }
  }, [])

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)

    if (!form.firstName.trim() || !form.lastName.trim()) {
      setError('First name and last name are required.')
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
            placeholder="Auto-generated if left blank"
          />
        </label>

        <label className="field">
          <span>School level (optional)</span>
          <select
            className="grade-input"
            value={form.schoolLevel}
            onChange={(event) => updateField('schoolLevel', event.target.value)}
            disabled={saving}
            style={{ width: '100%', textAlign: 'left' }}
          >
            <option value="">Not set</option>
            {SCHOOL_LEVELS.map((level) => (
              <option key={level.value} value={level.value}>
                {level.label}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Class / Classe (optional)</span>
          <ClassSelect
            classes={classes}
            value={form.classId}
            onChange={(value) => updateField('classId', value)}
            disabled={saving}
          />
        </label>

        <label className="field">
          <span>N° EducMaster (optional)</span>
          <input
            value={form.educmasterNumber}
            onChange={(event) => updateField('educmasterNumber', event.target.value)}
            disabled={saving}
            placeholder="Government-assigned, leave blank if unknown"
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
