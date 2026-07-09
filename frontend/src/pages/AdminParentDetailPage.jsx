import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
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
  const { t } = useTranslation()
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

    if (!editForm.name.trim()) {
      setEditError(t('parents.errorNameRequired'))
      return
    }

    setSavingEdit(true)
    try {
      await updateParent(parentId, editForm)
      const refreshed = await getParent(parentId)
      setParent(refreshed)
      setEditForm(parentToForm(refreshed))
      setEditMessage(t('parents.updated'))
      setShowEditForm(false)
    } catch (err) {
      setEditError(err.message)
    } finally {
      setSavingEdit(false)
    }
  }

  async function handleDeleteParent() {
    if (!window.confirm(t('parents.confirmDelete', { name: parent.name }))) return
    setEditError(null)
    setEditMessage(null)
    setDeleting(true)
    try {
      await deleteParent(parentId)
      navigate('/admin/parents', { replace: true, state: { message: t('parents.deleted') } })
    } catch (err) {
      if (err.status === 409 && err.detail && typeof err.detail === 'object') {
        setEditError(t('parents.deleteBlocked', { count: err.detail.active_student_count }))
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
          ← {t('nav.parents')}
        </Link>
        <ErrorBanner message={error} />
      </section>
    )
  }

  if (!parent) {
    return (
      <section className="admin-page">
        <Spinner label={t('parents.loadingOne')} />
      </section>
    )
  }

  return (
    <section className="admin-page">
      <Link to="/admin/parents" className="back-link">
        ← {t('nav.parents')}
      </Link>
      <div className="detail-header">
        <div>
          <h2 className="page-title">{parent.name}</h2>
          <p className="muted">
            {parent.email || '—'}
            {parent.phone ? ` · ${parent.phone}` : ''}
          </p>
        </div>
        {!showEditForm && (
          <div className="detail-actions">
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
              {t('common.edit')}
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-danger-subtle"
              onClick={handleDeleteParent}
              disabled={deleting}
            >
              {deleting ? t('common.deleting') : t('common.delete')}
            </button>
          </div>
        )}
      </div>
      {editMessage && <p className="grade-summary">{editMessage}</p>}
      {editError && !showEditForm && <ErrorBanner message={editError} />}
      {showEditForm && (
        <form className="card admin-form detail-form" onSubmit={handleEditParent}>
          <div className="section-heading">
            <h3>{t('common.edit')}</h3>
          </div>
          <label className="field">
            <span>{t('common.name')}</span>
            <input
              value={editForm.name}
              onChange={(event) => updateEditField('name', event.target.value)}
              disabled={savingEdit}
              required
            />
          </label>

          <label className="field">
            <span>{t('teachers.emailOptional')}</span>
            <input
              type="text"
              value={editForm.email}
              onChange={(event) => updateEditField('email', event.target.value)}
              disabled={savingEdit}
            />
          </label>

          <label className="field">
            <span>{t('common.phone')}</span>
            <input
              value={editForm.phone}
              onChange={(event) => updateEditField('phone', event.target.value)}
              disabled={savingEdit}
            />
          </label>

          <div className="grade-actions">
            <button type="submit" className="btn btn-primary" disabled={savingEdit}>
              {savingEdit ? t('common.saving') : t('common.saveChanges')}
            </button>
            <button type="button" className="btn btn-ghost" disabled={savingEdit} onClick={cancelEdit}>
              {t('common.cancel')}
            </button>
          </div>
          {editError && <ErrorBanner message={editError} />}
        </form>
      )}

      <div className="section-heading">
        <h3 className="section-title">{t('students.title')}</h3>
      </div>
      {students.length === 0 ? (
        <Empty message={t('parents.noStudents')} />
      ) : (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>{t('common.name')}</th>
                <th>{t('students.studentNumber')}</th>
                <th>{t('students.class')}</th>
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
                    <Link className="link-action" to={`/admin/students/${student.id}`}>
                      {t('common.open')}
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
