import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getTeacher, getTeacherCourses, updateTeacher } from '../api/teachers.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

function teacherToForm(teacher) {
  return {
    name: teacher?.name || '',
    email: teacher?.email || '',
    employeeNumber: teacher?.employee_number || '',
  }
}

export default function AdminTeacherDetailPage() {
  const { teacherId } = useParams()
  const [teacher, setTeacher] = useState(null)
  const [courses, setCourses] = useState([])
  const [error, setError] = useState(null)
  const [showEditForm, setShowEditForm] = useState(false)
  const [editForm, setEditForm] = useState(teacherToForm(null))
  const [savingEdit, setSavingEdit] = useState(false)
  const [editError, setEditError] = useState(null)
  const [editMessage, setEditMessage] = useState(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    setTeacher(null)
    setCourses([])
    setShowEditForm(false)
    setEditForm(teacherToForm(null))
    setSavingEdit(false)
    setEditError(null)
    setEditMessage(null)

    async function load() {
      try {
        const data = await getTeacher(teacherId)
        if (cancelled) return
        setTeacher(data)
        setEditForm(teacherToForm(data))
      } catch (err) {
        if (!cancelled) setError(err.message)
        return
      }
      // Assigned courses are best-effort.
      try {
        const list = await getTeacherCourses(teacherId)
        if (!cancelled) setCourses(list)
      } catch {
        /* non-fatal */
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [teacherId])

  function updateEditField(field, value) {
    setEditForm((current) => ({ ...current, [field]: value }))
  }

  function cancelEdit() {
    setEditForm(teacherToForm(teacher))
    setEditError(null)
    setShowEditForm(false)
  }

  async function handleEditTeacher(event) {
    event.preventDefault()
    setEditError(null)
    setEditMessage(null)

    if (!editForm.name.trim() || !editForm.email.trim() || !editForm.employeeNumber.trim()) {
      setEditError('Name, email, and employee number are required.')
      return
    }

    setSavingEdit(true)
    try {
      await updateTeacher(teacherId, editForm)
      const refreshed = await getTeacher(teacherId)
      setTeacher(refreshed)
      setEditForm(teacherToForm(refreshed))
      setEditMessage('Teacher updated.')
      setShowEditForm(false)
    } catch (err) {
      setEditError(err.message)
    } finally {
      setSavingEdit(false)
    }
  }

  if (error) {
    return (
      <section className="admin-page">
        <Link to="/admin/teachers" className="back-link">
          ← Teachers
        </Link>
        <ErrorBanner message={error} />
      </section>
    )
  }

  if (!teacher) {
    return (
      <section className="admin-page">
        <Spinner label="Loading teacher…" />
      </section>
    )
  }

  return (
    <section className="admin-page">
      <Link to="/admin/teachers" className="back-link">
        ← Teachers
      </Link>
      <h2 className="page-title">{teacher.name}</h2>
      <p className="muted">
        {teacher.email} · Employee #{teacher.employee_number}
      </p>
      {!showEditForm && (
        <div className="grade-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              setEditError(null)
              setEditMessage(null)
              setEditForm(teacherToForm(teacher))
              setShowEditForm(true)
            }}
          >
            Edit
          </button>
        </div>
      )}
      {editMessage && <p className="grade-summary">{editMessage}</p>}
      {showEditForm && (
        <form className="card admin-form" onSubmit={handleEditTeacher}>
          <label className="field">
            <span>Name</span>
            <input
              value={editForm.name}
              onChange={(event) => updateEditField('name', event.target.value)}
              disabled={savingEdit}
              required
            />
          </label>

          <label className="field">
            <span>Email</span>
            <input
              type="email"
              value={editForm.email}
              onChange={(event) => updateEditField('email', event.target.value)}
              disabled={savingEdit}
              required
            />
          </label>

          <label className="field">
            <span>Employee number</span>
            <input
              value={editForm.employeeNumber}
              onChange={(event) => updateEditField('employeeNumber', event.target.value)}
              disabled={savingEdit}
              required
            />
          </label>

          <div className="grade-actions">
            <button type="submit" className="btn btn-primary" disabled={savingEdit}>
              {savingEdit ? 'Saving...' : 'Save changes'}
            </button>
            <button type="button" className="btn btn-ghost" disabled={savingEdit} onClick={cancelEdit}>
              Cancel
            </button>
          </div>
          {editError && <ErrorBanner message={editError} />}
        </form>
      )}

      <h3 className="section-title">Assigned courses</h3>
      {courses.length === 0 ? (
        <Empty message="No courses assigned to this teacher." />
      ) : (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Code</th>
                <th>Grade level</th>
                <th>Term</th>
                <th>School year</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {courses.map((course) => (
                <tr key={course.id}>
                  <td>{course.name}</td>
                  <td className="nowrap">{course.code}</td>
                  <td className="nowrap">{course.grade_level}</td>
                  <td className="nowrap">{course.term}</td>
                  <td className="nowrap">{course.school_year}</td>
                  <td className="nowrap">
                    <Link className="back-link" to={`/admin/courses/${course.id}`}>
                      Open →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
