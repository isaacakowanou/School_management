import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { deleteTeacher, listTeachers } from '../api/teachers.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

export default function AdminTeachersPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const { t } = useTranslation()
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
    if (!window.confirm(t('teachers.confirmDelete', { name: teacher.name }))) return
    setError(null)
    setNotice(null)
    setDeletingId(teacher.id)
    try {
      await deleteTeacher(teacher.id)
      await refresh()
      setNotice(t('teachers.deleted'))
    } catch (err) {
      if (err.status === 409 && err.detail && typeof err.detail === 'object') {
        setError(t('teachers.deleteBlocked', { courses: err.detail.course_count, grades: err.detail.submitted_grade_count }))
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
          <h2 className="page-title">{t('nav.teachers')}</h2>
          <p className="muted">{t('teachers.subtitle')}</p>
        </div>
        <Link to="/admin/teachers/new" className="btn btn-primary">
          {t('teachers.addTeacher')}
        </Link>
      </div>

      {notice && <p className="grade-summary">{notice}</p>}
      {error && <ErrorBanner message={error} />}
      {!error && teachers === null && <Spinner label={t('teachers.loading')} />}
      {!error && teachers && teachers.length === 0 && <Empty message={t('teachers.empty')} />}
      {!error && teachers && teachers.length > 0 && (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>{t('common.name')}</th>
                <th>{t('common.email')}</th>
                <th>{t('common.phone')}</th>
                <th>{t('common.employeeNumber')}</th>
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
                      {t('common.open')}
                    </Link>
                    <button
                      type="button"
                      className="btn btn-ghost btn-small"
                      onClick={() => handleDelete(teacher)}
                      disabled={deletingId === teacher.id}
                      style={{ marginLeft: 8 }}
                    >
                      {deletingId === teacher.id ? t('common.deleting') : t('common.delete')}
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
