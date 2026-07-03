import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { deleteParent, listParents } from '../api/parents.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

export default function AdminParentsPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const [parents, setParents] = useState(null)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(location.state?.message || null)
  const [deletingId, setDeletingId] = useState(null)

  async function refresh() {
    const data = await listParents()
    setParents(data)
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
    setParents(null)
    refresh()
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

  async function handleDelete(parent) {
    if (!window.confirm(`Move parent "${parent.name}" to Trash? This is only allowed when the parent is not linked to active students.`)) return
    setError(null)
    setNotice(null)
    setDeletingId(parent.id)
    try {
      await deleteParent(parent.id)
      await refresh()
      setNotice('Parent deleted.')
    } catch (err) {
      if (err.status === 409 && err.detail && typeof err.detail === 'object') {
        setError(`Cannot delete "${parent.name}": linked to ${err.detail.active_student_count} active student(s).`)
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
          <h2 className="page-title">Parents</h2>
          <p className="muted">All parent accounts.</p>
        </div>
        <Link to="/admin/parents/new" className="btn btn-primary">
          Add parent
        </Link>
      </div>

      {notice && <p className="grade-summary">{notice}</p>}
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
                    <button
                      type="button"
                      className="btn btn-ghost btn-small"
                      onClick={() => handleDelete(parent)}
                      disabled={deletingId === parent.id}
                      style={{ marginLeft: 8 }}
                    >
                      {deletingId === parent.id ? 'Deleting...' : 'Delete'}
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
