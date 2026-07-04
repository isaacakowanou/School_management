import { Fragment, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getAuditLogs } from '../api/auditLogs.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

const EMPTY_FILTERS = { entity_type: '', entity_id: '', actor_user_id: '' }

function formatTime(iso) {
  if (!iso) return '—'
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString()
}

function formatJson(value) {
  if (value === null || value === undefined) return '—'
  if (Array.isArray(value) && value.length === 0) return '—'
  if (typeof value === 'object' && Object.keys(value).length === 0) return '—'
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function ActorCell({ log, unknownActorLabel }) {
  if (!log.actor_name && !log.actor_email) {
    return (
      <span className="audit-id" title={log.actor_user_id}>
        {log.actor_user_id}
      </span>
    )
  }

  return (
    <div>
      <div className="student-cell-main">{log.actor_name || unknownActorLabel}</div>
      {log.actor_email && <div className="student-cell-meta">{log.actor_email}</div>}
    </div>
  )
}

export default function AuditLogsPage() {
  const { t } = useTranslation()
  const [draft, setDraft] = useState(EMPTY_FILTERS)
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [logs, setLogs] = useState(null)
  const [error, setError] = useState(null)
  const [expandedLogId, setExpandedLogId] = useState(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    setLogs(null)
    setExpandedLogId(null)
    getAuditLogs(filters)
      .then((data) => {
        if (!cancelled) setLogs(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [filters])

  function applyFilters(event) {
    event.preventDefault()
    setFilters({
      entity_type: draft.entity_type.trim(),
      entity_id: draft.entity_id.trim(),
      actor_user_id: draft.actor_user_id.trim(),
    })
  }

  function clearFilters() {
    setDraft(EMPTY_FILTERS)
    setFilters(EMPTY_FILTERS)
  }

  function toggleDetails(logId) {
    setExpandedLogId((current) => (current === logId ? null : logId))
  }

  return (
    <section className="admin-page">
      <h2 className="page-title">{t('nav.auditLogs')}</h2>
      <p className="muted">{t('auditLogs.adminView')}</p>

      <form className="filters" onSubmit={applyFilters}>
        <label className="field">
          <span>{t('auditLogs.entityTypeFilter')}</span>
          <input
            value={draft.entity_type}
            onChange={(e) => setDraft({ ...draft, entity_type: e.target.value })}
            placeholder="e.g. report_card"
          />
        </label>
        <label className="field">
          <span>{t('auditLogs.entityId')}</span>
          <input
            value={draft.entity_id}
            onChange={(e) => setDraft({ ...draft, entity_id: e.target.value })}
            placeholder="UUID"
          />
        </label>
        <label className="field">
          <span>{t('auditLogs.actorId')}</span>
          <input
            value={draft.actor_user_id}
            onChange={(e) => setDraft({ ...draft, actor_user_id: e.target.value })}
            placeholder="UUID"
          />
        </label>
        <div className="filters-actions">
          <button type="submit" className="btn btn-primary">
            {t('common.apply')}
          </button>
          <button type="button" className="btn btn-ghost" onClick={clearFilters}>
            {t('common.clear')}
          </button>
        </div>
      </form>

      {error && <ErrorBanner message={error} />}
      {!error && logs === null && <Spinner label={t('auditLogs.loading')} />}
      {!error && logs && logs.length === 0 && <Empty message={t('auditLogs.empty')} />}
      {!error && logs && logs.length > 0 && (
        <div className="table-scroll">
          <table className="table audit-table">
            <thead>
              <tr>
                <th>{t('auditLogs.timeCol')}</th>
                <th>{t('auditLogs.actorCol')}</th>
                <th>{t('auditLogs.actionCol')}</th>
                <th>{t('auditLogs.entityTypeCol')}</th>
                <th>{t('auditLogs.entityIdCol')}</th>
                <th>{t('auditLogs.detailsCol')}</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => {
                const isExpanded = expandedLogId === log.id
                const oldValue = formatJson(log.old_value)
                const newValue = formatJson(log.new_value)
                return (
                  <Fragment key={log.id}>
                    <tr>
                      <td className="nowrap">{formatTime(log.created_at)}</td>
                      <td>
                        <ActorCell log={log} unknownActorLabel={t('auditLogs.unknownActor')} />
                      </td>
                      <td>{log.action}</td>
                      <td className="nowrap">{log.entity_type}</td>
                      <td>
                        <span className="audit-id" title={log.entity_id}>
                          {log.entity_id}
                        </span>
                      </td>
                      <td className="nowrap">
                        <button
                          type="button"
                          className="btn btn-ghost btn-small"
                          onClick={() => toggleDetails(log.id)}
                          aria-expanded={isExpanded}
                        >
                          {isExpanded ? t('auditLogs.hideDetails') : t('auditLogs.viewDetails')}
                        </button>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr className="audit-details-row">
                        <td colSpan={6}>
                          <div className="audit-details-grid">
                            <div>
                              <h3>{t('auditLogs.oldValue')}</h3>
                              <pre className="json-cell json-cell-expanded">{oldValue}</pre>
                            </div>
                            <div>
                              <h3>{t('auditLogs.newValue')}</h3>
                              <pre className="json-cell json-cell-expanded">{newValue}</pre>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
