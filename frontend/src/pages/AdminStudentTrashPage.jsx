import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listDeletedStudents, restoreStudent } from '../api/students.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

export default function AdminStudentTrashPage() {
  const [students, setStudents] = useState(null)
  const [error, setError] = useState(null)
  const [message, setMessage] = useState(null)
  const [restoringId, setRestoringId] = useState(null)

  async function refresh() {
    const data = await listDeletedStudents()
    setStudents(data)
    return data
  }

  useEffect(() => {
    let cancelled = false
    setError(null)
    setStudents(null)
    listDeletedStudents()
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

  async function handleRestore(student) {
    const name = `${student.first_name} ${student.last_name}`
    setError(null)
    setMessage(null)
    setRestoringId(student.id)
    try {
      await restoreStudent(student.id)
      await refresh()
      setMessage(`${name} restored.`)
    } catch (err) {
      setError(err.message)
    } finally {
      setRestoringId(null)
    }
  }

  return (
    <section className="admin-page">
      <Link to="/admin/students" className="back-link">
        ← Back to students
      </Link>

      <div className="report-header">
        <div>
          <h2 className="page-title">Deleted students</h2>
          <p className="muted">Students in Trash are hidden from normal workflows and can be restored.</p>
        </div>
      </div>

      {message && <p className="grade-summary">{message}</p>}
      {error && <ErrorBanner message={error} />}
      {!error && students === null && <Spinner label="Loading deleted students…" />}
      {!error && students && students.length === 0 && <Empty message="No deleted students." />}
      {!error && students && students.length > 0 && (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Student #</th>
                <th>Class</th>
                <th>Deleted</th>
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
                  <td className="nowrap">{new Date(student.deleted_at).toLocaleString()}</td>
                  <td className="nowrap">
                    <button
                      type="button"
                      className="btn btn-primary btn-small"
                      onClick={() => handleRestore(student)}
                      disabled={restoringId === student.id}
                    >
                      {restoringId === student.id ? 'Restoring...' : 'Restore'}
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
