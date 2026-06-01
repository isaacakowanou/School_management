import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'
import { getParentStudents } from '../api/parents.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

export default function DashboardPage() {
  const { parentId, parent } = useAuth()
  const [students, setStudents] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!parentId) return
    let cancelled = false
    setError(null)
    setStudents(null)
    getParentStudents(parentId)
      .then((data) => {
        if (!cancelled) setStudents(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [parentId])

  return (
    <section>
      <h2 className="page-title">My students</h2>
      {parent && <p className="muted">Signed in as {parent.name}</p>}

      {error && <ErrorBanner message={error} />}
      {!error && students === null && <Spinner label="Loading students…" />}
      {!error && students && students.length === 0 && (
        <Empty message="No students are linked to your account yet." />
      )}
      {!error && students && students.length > 0 && (
        <ul className="card-list">
          {students.map((student) => (
            <li key={student.id}>
              <Link className="card student-card" to={`/students/${student.id}/reports`}>
                <div className="student-name">
                  {student.first_name} {student.last_name}
                </div>
                <div className="muted">
                  {student.grade_level} · #{student.student_number}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
