// Unified Corbeille UI: batch deletions and standalone soft-deletes arrive in
// one response, while entity-specific deleted pages request filtered views of
// that same API. Restore is recoverable; purge/empty confirmations are styled
// and explicit because those actions permanently remove the selected trees.
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { emptyTrash, listTrash, purgeTrashEntry, restoreTrashEntry } from '../api/trash.js'
import Empty from '../components/Empty.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Spinner from '../components/Spinner.jsx'

function CountsSummary({ counts }) {
  return Object.entries(counts || {})
    .map(([table, count]) => `${table}: ${count}`)
    .join(', ')
}

function countTotal(summary) {
  return Object.values(summary || {}).reduce((total, count) => total + count, 0)
}

function summaryLines(summary, t) {
  return Object.entries(summary || {})
    .map(([type, count]) => `${t(`trash.types.${type}`, { defaultValue: type })}: ${count}`)
    .join('\n')
}

export default function AdminTrashPage() {
  const { t } = useTranslation()
  const [trash, setTrash] = useState(null)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [restoringId, setRestoringId] = useState(null)
  const [purgingId, setPurgingId] = useState(null)
  const [emptying, setEmptying] = useState(false)
  const [purgeConfirmEntry, setPurgeConfirmEntry] = useState(null)
  const [showEmptyConfirm, setShowEmptyConfirm] = useState(false)

  async function refresh() {
    const data = await listTrash()
    setTrash(data)
    return data
  }

  useEffect(() => {
    let cancelled = false
    setError(null)
    setTrash(null)
    listTrash()
      .then((data) => {
        if (!cancelled) setTrash(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function handleRestore(entry) {
    if (!window.confirm(t('trash.confirmRestore', { label: entry.target_label }))) return
    setError(null)
    setNotice(null)
    setRestoringId(entry.id)
    try {
      await restoreTrashEntry(entry.id)
      await refresh()
      setNotice(t('trash.restored', { label: entry.target_label }))
    } catch (err) {
      setError(err.message)
    } finally {
      setRestoringId(null)
    }
  }

  async function handlePurge(entry) {
    setError(null)
    setNotice(null)
    setPurgingId(entry.id)
    try {
      await purgeTrashEntry(entry.id)
      await refresh()
      setNotice(t('trash.purged', { label: entry.target_label }))
      setPurgeConfirmEntry(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setPurgingId(null)
    }
  }

  async function handleEmpty() {
    setError(null)
    setNotice(null)
    setEmptying(true)
    try {
      await emptyTrash()
      await refresh()
      setNotice(t('trash.emptied'))
      setShowEmptyConfirm(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setEmptying(false)
    }
  }

  const entries = trash?.entries || []
  const summary = trash?.summary || {}
  const total = countTotal(summary)
  const students = summary.student || 0
  const summaryText = summaryLines(summary, t)

  return (
    <section className="admin-page">
      <div className="report-header">
        <div>
          <h2 className="page-title">{t('nav.trash')}</h2>
          <p className="muted">
            {t('trash.subtitle')} {trash?.retention_days ? t('trash.retention', { days: trash.retention_days }) : ''}
          </p>
        </div>
        {entries.length > 0 && (
          <button type="button" className="btn btn-danger" disabled={emptying} onClick={() => setShowEmptyConfirm(true)}>
            {emptying ? t('trash.emptying') : t('trash.emptyTrash')}
          </button>
        )}
      </div>

      {notice && <p className="grade-summary">{notice}</p>}
      {error && <ErrorBanner message={error} />}
      {!error && trash === null && <Spinner label={t('trash.loading')} />}
      {!error && trash && entries.length === 0 && <Empty message={t('trash.empty')} />}
      {!error && trash && entries.length > 0 && (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>{t('trash.targetCol')}</th>
                <th>{t('trash.typeCol')}</th>
                <th>{t('trash.deletedCol')}</th>
                <th>{t('trash.countsCol')}</th>
                <th>{t('trash.statusCol')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.id}>
                  <td>{entry.target_label}</td>
                  <td className="nowrap">{t(`trash.types.${entry.entity_type}`, { defaultValue: entry.entity_type })}</td>
                  <td className="nowrap">{new Date(entry.deleted_at).toLocaleString()}</td>
                  <td>{CountsSummary({ counts: entry.counts })}</td>
                  <td className="nowrap">{entry.restored_at ? t('trash.statusRestored') : t('trash.statusInTrash')}</td>
                  <td className="nowrap">
                    <button
                      type="button"
                      className="btn btn-primary btn-small"
                      disabled={Boolean(entry.restored_at) || restoringId === entry.id || purgingId === entry.id}
                      onClick={() => handleRestore(entry)}
                    >
                      {restoringId === entry.id ? t('trash.restoring') : t('trash.restore')}
                    </button>
                    <button
                      type="button"
                      className="btn btn-danger btn-small"
                      disabled={Boolean(entry.restored_at) || restoringId === entry.id || purgingId === entry.id}
                      onClick={() => setPurgeConfirmEntry(entry)}
                    >
                      {purgingId === entry.id ? t('trash.purging') : t('trash.purge')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {purgeConfirmEntry && (
        <div className="modal-backdrop" onClick={() => !purgingId && setPurgeConfirmEntry(null)}>
          <div className="card modal-card" onClick={(event) => event.stopPropagation()}>
            <h3>{t('trash.purge')}</h3>
            <p>{t('trash.confirmPurgeEntry', { label: purgeConfirmEntry.target_label })}</p>
            <div className="form-actions">
              <button type="button" className="btn btn-ghost" disabled={Boolean(purgingId)} onClick={() => setPurgeConfirmEntry(null)}>
                {t('common.cancel')}
              </button>
              <button type="button" className="btn btn-danger" disabled={Boolean(purgingId)} onClick={() => handlePurge(purgeConfirmEntry)}>
                {purgingId === purgeConfirmEntry.id ? t('trash.purging') : t('trash.purge')}
              </button>
            </div>
          </div>
        </div>
      )}

      {showEmptyConfirm && (
        <div className="modal-backdrop" onClick={() => !emptying && setShowEmptyConfirm(false)}>
          <div className="card modal-card" onClick={(event) => event.stopPropagation()}>
            <h3>{t('trash.emptyTrash')}</h3>
            <p style={{ whiteSpace: 'pre-line' }}>{t('trash.confirmEmpty', { total, students, summary: summaryText })}</p>
            <div className="form-actions">
              <button type="button" className="btn btn-ghost" disabled={emptying} onClick={() => setShowEmptyConfirm(false)}>
                {t('common.cancel')}
              </button>
              <button type="button" className="btn btn-danger" disabled={emptying} onClick={handleEmpty}>
                {emptying ? t('trash.emptying') : t('trash.emptyTrash')}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
