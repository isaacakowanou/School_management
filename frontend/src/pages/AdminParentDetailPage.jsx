import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getParent, getParentStudents } from '../api/parents.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

export default function AdminParentDetailPage() {
  const { parentId } = useParams()
  const [parent, setParent] = useState(null)
  const [students, setStudents] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    setParent(null)
    setStudents([])

    async function load() {
      try {
        const data = await getParent(parentId)
        if (cancelled) return
        setParent(data)
      } catch (err) {
        if (!cancelled) setError(err.message)
        return
      }
      // Linked students are best-effort; a failure here won't blank the page.
      try {
        const linked = await getParentStudents(parentId)
        if (!cancelled) setStudents(linked)
      } catch {
        /* non-fatal */
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [parentId])

  if (error) {
    return (
      <section className="admin-page">
        <Link to="/admin/parents" className="back-link">
          ← Parents
        </Link>
        <ErrorBanner message={error} />
      </section>
    )
  }

  if (!parent) {
    return (
      <section className="admin-page">
        <Spinner label="Loading parent…" />
      </section>
    )
  }

  return (
    <section className="admin-page">
      <Link to="/admin/parents" className="back-link">
        ← Parents
      </Link>
      <h2 className="page-title">{parent.name}</h2>
      <p className="muted">
        {parent.email}
        {parent.phone ? ` · ${parent.phone}` : ''}
      </p>

      <h3 className="section-title">Linked students</h3>
      {students.length === 0 ? (
        <Empty message="No students linked to this parent." />
      ) : (
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
