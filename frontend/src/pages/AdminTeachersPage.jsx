import { useEffect, useMemo, useState } from 'react'
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
  const [search, setSearch] = useState('')
  const [visibleCount, setVisibleCount] = useState(25)
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

  const filteredTeachers = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return teachers || []
    return (teachers || []).filter((teacher) =>
      `${teacher.name} ${teacher.email || ''} ${teacher.phone || ''} ${teacher.employee_number || ''}`.toLowerCase().includes(query),
    )
  }, [teachers, search])

  const visibleTeachers = filteredTeachers.slice(0, visibleCount)

  return (
    <section className="admin-page">
      <div className="report-header">
        <div>
          <h2 className="page-title">{t('nav.teachers')}</h2>
          <p className="muted">{t('teachers.count', { count: teachers?.length ?? 0 })}</p>
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
        <div className="list-stack">
          <div className="list-toolbar">
            <label className="toolbar-field">
              <span>{t('common.search')}</span>
              <input
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value)
                  setVisibleCount(25)
                }}
                placeholder={t('teachers.searchPlaceholder')}
              />
            </label>
          </div>
          {filteredTeachers.length === 0 ? (
            <Empty message={t('teachers.emptyFiltered')} />
          ) : (
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
                  {visibleTeachers.map((teacher) => (
                    <tr key={teacher.id}>
                      <td>{teacher.name}</td>
                      <td className="nowrap">{teacher.email || '—'}</td>
                      <td className="nowrap">{teacher.phone || '—'}</td>
                      <td className="nowrap">{teacher.employee_number}</td>
                      <td className="nowrap row-actions">
                        <Link className="link-action" to={`/admin/teachers/${teacher.id}`}>
                          {t('common.open')}
                        </Link>
                        <button
                          type="button"
                          className="link-action link-action-danger"
                          onClick={() => handleDelete(teacher)}
                          disabled={deletingId === teacher.id}
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
          {filteredTeachers.length > visibleCount && (
            <button type="button" className="btn btn-ghost show-more-btn" onClick={() => setVisibleCount((count) => count + 25)}>
              {t('common.showMore', { count: Math.min(25, filteredTeachers.length - visibleCount) })}
            </button>
          )}
        </div>
      )}
    </section>
  )
}
