import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listStudents } from '../api/students.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

export default function AdminStudentsPage() {
  const [students, setStudents] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    setStudents(null)
    listStudents()
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

  return (
    <section className="admin-page">
      <h2 className="page-title">Students</h2>
      <p className="muted">All students, read-only.</p>

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
                <th>Grade level</th>
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
                  <td className="nowrap">{student.grade_level}</td>
                  <td className="nowrap">
                    <Link className="back-link" to={`/admin/students/${student.id}`}>
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
