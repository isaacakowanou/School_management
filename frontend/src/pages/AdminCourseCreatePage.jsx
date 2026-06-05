import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { createCourse } from '../api/courses.js'
import { listTeachers } from '../api/teachers.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

const EMPTY_FORM = {
  name: '',
  code: '',
  teacherId: '',
  gradeLevel: '',
  term: '',
  schoolYear: '',
}

const GRADE_LEVEL_SUGGESTIONS = [
  'Grade 6',
  'Grade 7',
  'Grade 8',
  'Grade 9',
  'Grade 10',
  'Grade 11',
  'Grade 12',
]

const TERM_SUGGESTIONS = ['Fall', 'Spring', 'Summer', 'Trimester 1', 'Trimester 2', 'Trimester 3']
const SCHOOL_YEAR_SUGGESTIONS = ['2026-2027', '2027-2028', '2028-2029']

export default function AdminCourseCreatePage() {
  const navigate = useNavigate()
  const [form, setForm] = useState(EMPTY_FORM)
  const [teachers, setTeachers] = useState(null)
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    setError(null)
    setTeachers(null)

    listTeachers()
      .then((data) => {
        if (cancelled) return
        setTeachers(data)
        setForm((current) => ({
          ...current,
          teacherId: current.teacherId || data[0]?.id || '',
        }))
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
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

    if (
      !form.name.trim() ||
      !form.code.trim() ||
      !form.teacherId ||
      !form.gradeLevel.trim() ||
      !form.term.trim() ||
      !form.schoolYear.trim()
    ) {
      setError('Course name, code, teacher, grade level, term, and school year are required.')
      return
    }

    setSaving(true)
    try {
      await createCourse(form)
      navigate('/admin/courses', {
        state: { message: 'Course created.' },
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="admin-page">
      <Link to="/admin/courses" className="back-link">
        &lt;- Courses
      </Link>

      <div className="report-header">
        <div>
          <h2 className="page-title">Add course</h2>
          <p className="muted">Create a course and assign its teacher.</p>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}
      {!error && teachers === null && <Spinner label="Loading teachers..." />}
      {!error && teachers && teachers.length === 0 && (
        <Empty message="Create a teacher before adding a course." />
      )}

      {teachers && teachers.length > 0 && (
        <form className="card admin-form" onSubmit={handleSubmit}>
          <label className="field">
            <span>Course name</span>
            <input
              value={form.name}
              onChange={(event) => updateField('name', event.target.value)}
              disabled={saving}
              required
            />
          </label>

          <label className="field">
            <span>Course code</span>
            <input
              value={form.code}
              onChange={(event) => updateField('code', event.target.value)}
              disabled={saving}
              required
            />
          </label>

          <label className="field">
            <span>Teacher</span>
            <select
              className="grade-input"
              value={form.teacherId}
              onChange={(event) => updateField('teacherId', event.target.value)}
              disabled={saving}
              required
              style={{ width: '100%', textAlign: 'left' }}
            >
              {teachers.map((teacher) => (
                <option key={teacher.id} value={teacher.id}>
                  {teacher.name} — {teacher.email} — #{teacher.employee_number}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Grade level</span>
            <input
              value={form.gradeLevel}
              onChange={(event) => updateField('gradeLevel', event.target.value)}
              disabled={saving}
              list="course-grade-level-options"
              required
            />
          </label>

          <label className="field">
            <span>Term</span>
            <input
              value={form.term}
              onChange={(event) => updateField('term', event.target.value)}
              disabled={saving}
              list="course-term-options"
              required
            />
          </label>

          <label className="field">
            <span>School year</span>
            <input
              value={form.schoolYear}
              onChange={(event) => updateField('schoolYear', event.target.value)}
              disabled={saving}
              list="course-school-year-options"
              required
            />
          </label>

          <datalist id="course-grade-level-options">
            {GRADE_LEVEL_SUGGESTIONS.map((value) => (
              <option key={value} value={value} />
            ))}
          </datalist>
          <datalist id="course-term-options">
            {TERM_SUGGESTIONS.map((value) => (
              <option key={value} value={value} />
            ))}
          </datalist>
          <datalist id="course-school-year-options">
            {SCHOOL_YEAR_SUGGESTIONS.map((value) => (
              <option key={value} value={value} />
            ))}
          </datalist>

          <div className="grade-actions">
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? 'Creating...' : 'Create course'}
            </button>
            <Link to="/admin/courses" className="btn btn-ghost">
              Cancel
            </Link>
          </div>
        </form>
      )}
    </section>
  )
}
