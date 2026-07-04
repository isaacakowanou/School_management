import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { deleteTeacher, listTeachers } from '../api/teachers.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

export default function AdminTeachersPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const [teachers, setTeachers] = useState(null)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(location.state?.message || null)
  const [deletingId, setDeletingId] = useState(null)

  async function refresh() {
    const data = await listTeachers()
    setTeachers(data)
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
    setTeachers(null)
    refresh()
      .then((data) => {
        if (!cancelled) setTeachers(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function handleDelete(teacher) {
    if (!window.confirm(`Move teacher "${teacher.name}" to Trash? This is only allowed when the teacher has no courses or submitted grades.`)) return
    setError(null)
    setNotice(null)
    setDeletingId(teacher.id)
    try {
      await deleteTeacher(teacher.id)
      await refresh()
      setNotice('Teacher deleted.')
    } catch (err) {
      if (err.status === 409 && err.detail && typeof err.detail === 'object') {
        setError(
          `Cannot delete "${teacher.name}": ${err.detail.course_count} course(s) and ` +
            `${err.detail.submitted_grade_count} submitted grade(s) are still linked.`,
        )
      } else {
        setError(err.message)
      }
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <section className="admin-page">
      <div className="report-header">
        <div>
          <h2 className="page-title">Teachers</h2>
          <p className="muted">All teacher accounts.</p>
        </div>
        <Link to="/admin/teachers/new" className="btn btn-primary">
          Add teacher
        </Link>
      </div>

      {notice && <p className="grade-summary">{notice}</p>}
      {error && <ErrorBanner message={error} />}
      {!error && teachers === null && <Spinner label="Loading teachers…" />}
      {!error && teachers && teachers.length === 0 && <Empty message="No teachers found." />}
      {!error && teachers && teachers.length > 0 && (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Phone</th>
                <th>Employee #</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {teachers.map((teacher) => (
                <tr key={teacher.id}>
                  <td>{teacher.name}</td>
                  <td className="nowrap">{teacher.email || '—'}</td>
                  <td className="nowrap">{teacher.phone || '—'}</td>
                  <td className="nowrap">{teacher.employee_number}</td>
                  <td className="nowrap">
                    <Link className="back-link" to={`/admin/teachers/${teacher.id}`}>
                      Open →
                    </Link>
                    <button
                      type="button"
                      className="btn btn-ghost btn-small"
                      onClick={() => handleDelete(teacher)}
                      disabled={deletingId === teacher.id}
                      style={{ marginLeft: 8 }}
                    >
                      {deletingId === teacher.id ? 'Deleting...' : 'Delete'}
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
