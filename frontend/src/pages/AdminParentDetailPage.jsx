import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { deleteParent, getParent, getParentStudents, updateParent } from '../api/parents.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

function parentToForm(parent) {
  return {
    name: parent?.name || '',
    email: parent?.email || '',
    phone: parent?.phone || '',
  }
}

export default function AdminParentDetailPage() {
  const { parentId } = useParams()
  const navigate = useNavigate()
  const [parent, setParent] = useState(null)
  const [students, setStudents] = useState([])
  const [error, setError] = useState(null)
  const [showEditForm, setShowEditForm] = useState(false)
  const [editForm, setEditForm] = useState(parentToForm(null))
  const [savingEdit, setSavingEdit] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [editError, setEditError] = useState(null)
  const [editMessage, setEditMessage] = useState(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    setParent(null)
    setStudents([])
    setShowEditForm(false)
    setEditForm(parentToForm(null))
    setSavingEdit(false)
    setDeleting(false)
    setEditError(null)
    setEditMessage(null)

    async function load() {
      try {
        const data = await getParent(parentId)
        if (cancelled) return
        setParent(data)
        setEditForm(parentToForm(data))
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

  function updateEditField(field, value) {
    setEditForm((current) => ({ ...current, [field]: value }))
  }

  function cancelEdit() {
    setEditForm(parentToForm(parent))
    setEditError(null)
    setShowEditForm(false)
  }

  async function handleEditParent(event) {
    event.preventDefault()
    setEditError(null)
    setEditMessage(null)

    if (!editForm.name.trim() || !editForm.email.trim()) {
      setEditError('Name and email are required.')
      return
    }

    setSavingEdit(true)
    try {
      await updateParent(parentId, editForm)
      const refreshed = await getParent(parentId)
      setParent(refreshed)
      setEditForm(parentToForm(refreshed))
      setEditMessage('Parent updated.')
      setShowEditForm(false)
    } catch (err) {
      setEditError(err.message)
    } finally {
      setSavingEdit(false)
    }
  }

  async function handleDeleteParent() {
    if (!window.confirm(`Move parent "${parent.name}" to Trash? This is only allowed when the parent is not linked to active students.`)) return
    setEditError(null)
    setEditMessage(null)
    setDeleting(true)
    try {
      await deleteParent(parentId)
      navigate('/admin/parents', { replace: true, state: { message: 'Parent deleted.' } })
    } catch (err) {
      if (err.status === 409 && err.detail && typeof err.detail === 'object') {
        setEditError(`Cannot delete this parent: linked to ${err.detail.active_student_count} active student(s).`)
      } else {
        setEditError(err.message)
      }
    } finally {
      setDeleting(false)
    }
  }

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
      {!showEditForm && (
        <div className="grade-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              setEditError(null)
              setEditMessage(null)
              setEditForm(parentToForm(parent))
              setShowEditForm(true)
            }}
          >
            Edit
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={handleDeleteParent}
            disabled={deleting}
          >
            {deleting ? 'Deleting...' : 'Delete'}
          </button>
        </div>
      )}
      {editMessage && <p className="grade-summary">{editMessage}</p>}
      {editError && !showEditForm && <ErrorBanner message={editError} />}
      {showEditForm && (
        <form className="card admin-form" onSubmit={handleEditParent}>
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
            <span>Phone</span>
            <input
              value={editForm.phone}
              onChange={(event) => updateEditField('phone', event.target.value)}
              disabled={savingEdit}
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

      <h3 className="section-title">Students</h3>
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
