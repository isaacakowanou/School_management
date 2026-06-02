import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listParents } from '../api/parents.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

export default function AdminParentsPage() {
  const [parents, setParents] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    setParents(null)
    listParents()
      .then((data) => {
        if (!cancelled) setParents(data)
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
      <h2 className="page-title">Parents</h2>
      <p className="muted">All parent accounts, read-only.</p>

      {error && <ErrorBanner message={error} />}
      {!error && parents === null && <Spinner label="Loading parents…" />}
      {!error && parents && parents.length === 0 && <Empty message="No parents found." />}
      {!error && parents && parents.length > 0 && (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Phone</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {parents.map((parent) => (
                <tr key={parent.id}>
                  <td>{parent.name}</td>
                  <td className="nowrap">{parent.email}</td>
                  <td className="nowrap">{parent.phone || '—'}</td>
                  <td className="nowrap">
                    <Link className="back-link" to={`/admin/parents/${parent.id}`}>
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
