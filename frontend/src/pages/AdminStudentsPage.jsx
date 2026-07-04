import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { deleteStudent, listStudents } from '../api/students.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

export default function AdminStudentsPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const [students, setStudents] = useState(null)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(location.state?.message || null)
  const [deletingId, setDeletingId] = useState(null)

  async function refresh() {
    const data = await listStudents()
    setStudents(data)
    return data
  }

  useEffect(() => {
    if (location.state?.message) {
      navigate(location.pathname, { replace: true, state: {} })
    }
  }, [location.pathname, location.state, navigate])

  useEffect(() => {
    let cancelled = false
    setError(null)
    setStudents(null)
    refresh()
      .then((data) => {
        if (!cancelled) setStudents(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function handleDelete(student) {
    const name = `${student.first_name} ${student.last_name}`
    if (!window.confirm(`Move ${name} to Trash? This hides the student from normal workflows and can be restored.`)) {
      return
    }
    setError(null)
    setNotice(null)
    setDeletingId(student.id)
    try {
      await deleteStudent(student.id)
      await refresh()
      setNotice(`${name} moved to Trash.`)
    } catch (err) {
      setError(err.message)
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <section className="admin-page">
      <div className="report-header">
        <div>
          <h2 className="page-title">Students</h2>
          <p className="muted">All students.</p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <Link to="/admin/students/trash" className="btn btn-ghost">
            Deleted students
          </Link>
          <Link to="/admin/students/new" className="btn btn-primary">
            Add student
          </Link>
        </div>
      </div>

      {notice && <p className="grade-summary">{notice}</p>}
      {error && <ErrorBanner message={error} />}
      {!error && students === null && <Spinner label="Loading students…" />}
      {!error && students && students.length === 0 && <Empty message="No students found." />}
      {!error && students && students.length > 0 && (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Student #</th>
                <th>Class</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {students.map((student) => (
                <tr key={student.id}>
                  <td>
                    {student.first_name} {student.last_name}
                  </td>
                  <td className="nowrap">{student.student_number}</td>
                  <td className="nowrap">{student.class_name || '—'}</td>
                  <td className="nowrap">
                    <Link className="back-link" to={`/admin/students/${student.id}`}>
                      Open →
                    </Link>
                    <button
                      type="button"
                      className="btn btn-ghost btn-small"
                      onClick={() => handleDelete(student)}
                      disabled={deletingId === student.id}
                      style={{ marginLeft: 8 }}
                    >
                      {deletingId === student.id ? 'Moving...' : 'Delete'}
                    </button>
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
