import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { listDeletionBatches, restoreDeletionBatch } from '../api/dangerZone.js'
import Empty from '../components/Empty.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Spinner from '../components/Spinner.jsx'

function CountsSummary({ counts }) {
  return Object.entries(counts || {})
    .map(([table, count]) => `${table}: ${count}`)
    .join(', ')
}

export default function AdminTrashPage() {
  const { t } = useTranslation()
  const [batches, setBatches] = useState(null)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [restoringId, setRestoringId] = useState(null)

  async function refresh() {
    const data = await listDeletionBatches()
    setBatches(data)
    return data
  }

  useEffect(() => {
    let cancelled = false
    setError(null)
    setBatches(null)
    listDeletionBatches()
      .then((data) => {
        if (!cancelled) setBatches(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function handleRestore(batch) {
    if (!window.confirm(t('trash.confirmRestore', { label: batch.target_label }))) return
    setError(null)
    setNotice(null)
    setRestoringId(batch.id)
    try {
      await restoreDeletionBatch(batch.id)
      await refresh()
      setNotice(t('trash.restored', { label: batch.target_label }))
    } catch (err) {
      setError(err.message)
    } finally {
      setRestoringId(null)
    }
  }

  return (
    <section className="admin-page">
      <div className="report-header">
        <div>
          <h2 className="page-title">{t('nav.trash')}</h2>
          <p className="muted">{t('trash.subtitle')}</p>
        </div>
      </div>

      {notice && <p className="grade-summary">{notice}</p>}
      {error && <ErrorBanner message={error} />}
      {!error && batches === null && <Spinner label={t('trash.loading')} />}
      {!error && batches && batches.length === 0 && <Empty message={t('trash.empty')} />}
      {!error && batches && batches.length > 0 && (
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
              {batches.map((batch) => (
                <tr key={batch.id}>
                  <td>{batch.target_label}</td>
                  <td className="nowrap">{batch.entity_type}</td>
                  <td className="nowrap">{new Date(batch.deleted_at).toLocaleString()}</td>
                  <td>{CountsSummary({ counts: batch.counts })}</td>
                  <td className="nowrap">{batch.restored_at ? t('trash.statusRestored') : t('trash.statusInTrash')}</td>
                  <td className="nowrap">
                    <button
                      type="button"
                      className="btn btn-primary btn-small"
                      disabled={Boolean(batch.restored_at) || restoringId === batch.id}
                      onClick={() => handleRestore(batch)}
                    >
                      {restoringId === batch.id ? t('trash.restoring') : t('trash.restore')}
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
