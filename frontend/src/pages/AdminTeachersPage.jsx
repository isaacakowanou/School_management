import { useEffect, useState } from 'react'
import { listTeachers } from '../api/teachers.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

export default function AdminTeachersPage() {
  const [teachers, setTeachers] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    setTeachers(null)
    listTeachers()
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

  return (
    <section className="admin-page">
      <h2 className="page-title">Teachers</h2>
      <p className="muted">All teacher accounts, read-only.</p>

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
                <th>Employee #</th>
              </tr>
            </thead>
            <tbody>
              {teachers.map((teacher) => (
                <tr key={teacher.id}>
                  <td>{teacher.name}</td>
                  <td className="nowrap">{teacher.email}</td>
                  <td className="nowrap">{teacher.employee_number}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
