import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { deleteStudent, listStudents } from '../api/students.js'
import { listClasses } from '../api/classes.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

export default function AdminStudentsPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [students, setStudents] = useState(null)
  const [classes, setClasses] = useState([])
  const [search, setSearch] = useState('')
  const [classFilter, setClassFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('active')
  const [visibleCount, setVisibleCount] = useState(25)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(location.state?.message || null)
  const [deletingId, setDeletingId] = useState(null)

  async function refresh() {
    const data = await listStudents({ academicStatus: statusFilter })
    setStudents(data)
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
    setStudents(null)
    refresh()
      .then((data) => {
        if (!cancelled) setStudents(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [statusFilter])

  useEffect(() => {
    let cancelled = false
    listClasses()
      .then((data) => {
        if (!cancelled) setClasses(data)
      })
      .catch(() => {
        /* non-fatal: filter just stays empty */
      })
    return () => {
      cancelled = true
    }
  }, [])

  const filteredStudents = useMemo(() => {
    const query = search.trim().toLowerCase()
    return (students || []).filter((student) => {
      const haystack = `${student.first_name} ${student.last_name} ${student.student_number || ''}`.toLowerCase()
      if (query && !haystack.includes(query)) return false
      if (classFilter === '__none__') return !student.class_id
      if (classFilter && student.class_id !== classFilter) return false
      return true
    })
  }, [students, search, classFilter])

  const visibleStudents = filteredStudents.slice(0, visibleCount)

  async function handleDelete(student) {
    const name = `${student.first_name} ${student.last_name}`
    if (!window.confirm(t('students.confirmDelete', { name }))) {
      return
    }
    setError(null)
    setNotice(null)
    setDeletingId(student.id)
    try {
      await deleteStudent(student.id)
      await refresh()
      setNotice(t('students.movedToTrash', { name }))
    } catch (err) {
      setError(err.message)
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <section className="admin-page">
      <div className="report-header">
        <div>
          <h2 className="page-title">{t('students.title')}</h2>
          <p className="muted">{t('students.count', { count: students?.length ?? 0 })}</p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <Link to="/admin/students/trash" className="btn btn-ghost">
            {t('students.deletedStudents')}
          </Link>
          <Link to="/admin/students/new" className="btn btn-primary">
            {t('students.addStudent')}
          </Link>
        </div>
      </div>

      {notice && <p className="grade-summary">{notice}</p>}
      {error && <ErrorBanner message={error} />}
      {!error && students === null && <Spinner label={t('students.loading')} />}
      {!error && students && students.length === 0 && <Empty message={t('students.empty')} />}
      {!error && students && students.length > 0 && (
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
                placeholder={t('students.searchPlaceholder')}
              />
            </label>
            <label className="toolbar-field">
              <span>{t('students.class')}</span>
              <select
                value={classFilter}
                onChange={(event) => {
                  setClassFilter(event.target.value)
                  setVisibleCount(25)
                }}
              >
                <option value="">{t('common.all')}</option>
                <option value="__none__">{t('common.unassigned')}</option>
                {classes.map((cls) => (
                  <option key={cls.id} value={cls.id}>
                    {cls.name_fr}{cls.name_en ? ` (${cls.name_en})` : ''} · {cls.school_year}
                  </option>
                ))}
              </select>
            </label>
            <label className="toolbar-field">
              <span>Statut</span>
              <select
                value={statusFilter}
                onChange={(event) => {
                  setStatusFilter(event.target.value)
                  setVisibleCount(25)
                }}
              >
                <option value="active">Actifs</option>
                <option value="graduated">Diplômés</option>
                <option value="all">{t('common.all')}</option>
              </select>
            </label>
          </div>

          {filteredStudents.length === 0 ? (
            <Empty message={t('students.emptyFiltered')} />
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
                  {visibleStudents.map((student) => (
                    <tr key={student.id}>
                      <td>
                        {student.first_name} {student.last_name}
                      </td>
                      <td className="nowrap">{student.student_number}</td>
                      <td className="nowrap">{student.class_name || '—'}</td>
                      <td className="nowrap row-actions">
                        <Link className="link-action" to={`/admin/students/${student.id}`}>
                          {t('common.open')}
                        </Link>
                        <button
                          type="button"
                          className="link-action link-action-danger"
                          onClick={() => handleDelete(student)}
                          disabled={deletingId === student.id}
                        >
                          {deletingId === student.id ? t('students.moving') : t('common.delete')}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {filteredStudents.length > visibleCount && (
            <button type="button" className="btn btn-ghost show-more-btn" onClick={() => setVisibleCount((count) => count + 25)}>
              {t('common.showMore', { count: Math.min(25, filteredStudents.length - visibleCount) })}
            </button>
          )}
        </div>
      )}
    </section>
  )
}
