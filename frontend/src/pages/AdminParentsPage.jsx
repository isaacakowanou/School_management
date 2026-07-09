import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { deleteParent, listParents } from '../api/parents.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

export default function AdminParentsPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [parents, setParents] = useState(null)
  const [search, setSearch] = useState('')
  const [visibleCount, setVisibleCount] = useState(25)
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
    if (!window.confirm(t('parents.confirmDelete', { name: parent.name }))) return
    setError(null)
    setNotice(null)
    setDeletingId(parent.id)
    try {
      await deleteParent(parent.id)
      await refresh()
      setNotice(t('parents.deleted'))
    } catch (err) {
      if (err.status === 409 && err.detail && typeof err.detail === 'object') {
        setError(t('parents.deleteBlocked', { count: err.detail.active_student_count }))
      } else {
        setError(err.message)
      }
    } finally {
      setDeletingId(null)
    }
  }

  const filteredParents = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return parents || []
    return (parents || []).filter((parent) =>
      `${parent.name} ${parent.email || ''} ${parent.phone || ''}`.toLowerCase().includes(query),
    )
  }, [parents, search])

  const visibleParents = filteredParents.slice(0, visibleCount)

  return (
    <section className="admin-page">
      <div className="report-header">
        <div>
          <h2 className="page-title">{t('nav.parents')}</h2>
          <p className="muted">{t('parents.count', { count: parents?.length ?? 0 })}</p>
        </div>
        <Link to="/admin/parents/new" className="btn btn-primary">
          {t('parents.addParent')}
        </Link>
      </div>

      {notice && <p className="grade-summary">{notice}</p>}
      {error && <ErrorBanner message={error} />}
      {!error && parents === null && <Spinner label={t('parents.loading')} />}
      {!error && parents && parents.length === 0 && <Empty message={t('parents.empty')} />}
      {!error && parents && parents.length > 0 && (
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
                placeholder={t('parents.searchPlaceholder')}
              />
            </label>
          </div>
          {filteredParents.length === 0 ? (
            <Empty message={t('parents.emptyFiltered')} />
          ) : (
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>{t('common.name')}</th>
                    <th>{t('common.email')}</th>
                    <th>{t('common.phone')}</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {visibleParents.map((parent) => (
                    <tr key={parent.id}>
                      <td>{parent.name}</td>
                      <td className="nowrap">{parent.email || '—'}</td>
                      <td className="nowrap">{parent.phone || '—'}</td>
                      <td className="nowrap row-actions">
                        <Link className="link-action" to={`/admin/parents/${parent.id}`}>
                          {t('common.open')}
                        </Link>
                        <button
                          type="button"
                          className="link-action link-action-danger"
                          onClick={() => handleDelete(parent)}
                          disabled={deletingId === parent.id}
                        >
                          {deletingId === parent.id ? t('common.deleting') : t('common.delete')}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {filteredParents.length > visibleCount && (
            <button type="button" className="btn btn-ghost show-more-btn" onClick={() => setVisibleCount((count) => count + 25)}>
              {t('common.showMore', { count: Math.min(25, filteredParents.length - visibleCount) })}
            </button>
          )}
        </div>
      )}
    </section>
  )
}
