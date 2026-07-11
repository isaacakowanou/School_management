import { Fragment, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getAuditLogs } from '../api/auditLogs.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

const EMPTY_FILTERS = { category: 'operational', entity_type: '', entity_id: '', actor_user_id: '', action: '', date_from: '', date_to: '' }

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
    return <span className="muted">{unknownActorLabel}</span>
  }

  return (
    <div>
      <div className="student-cell-main">{log.actor_name || unknownActorLabel}</div>
      {log.actor_email && <div className="student-cell-meta">{log.actor_email}</div>}
    </div>
  )
}

function actionLabel(t, action) {
  return t(`auditLogs.actions.${action}`, { defaultValue: action.replaceAll('_', ' ') })
}

export default function AuditLogsPage() {
  const { t } = useTranslation()
  const [draft, setDraft] = useState(EMPTY_FILTERS)
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [logs, setLogs] = useState(null)
  const [error, setError] = useState(null)
  const [expandedLogId, setExpandedLogId] = useState(null)
  const [visibleCount, setVisibleCount] = useState(25)
  const [copiedId, setCopiedId] = useState(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    setLogs(null)
    setExpandedLogId(null)
    setVisibleCount(25)
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
      category: draft.category,
      entity_type: draft.entity_type.trim(),
      entity_id: draft.entity_id.trim(),
      actor_user_id: draft.actor_user_id.trim(),
      action: draft.action,
      date_from: draft.date_from,
      date_to: draft.date_to,
    })
  }

  function clearFilters() {
    setDraft(EMPTY_FILTERS)
    setFilters(EMPTY_FILTERS)
  }

  function toggleDetails(logId) {
    setExpandedLogId((current) => (current === logId ? null : logId))
  }

  async function copyEntityId(value) {
    if (!value) return
    await navigator.clipboard.writeText(value)
    setCopiedId(value)
    window.setTimeout(() => setCopiedId(null), 1600)
  }

  const actionOptions = useMemo(() => {
    const set = new Set((logs || []).map((log) => log.action).filter(Boolean))
    if (draft.action) set.add(draft.action)
    return Array.from(set).sort()
  }, [logs, draft.action])

  const filteredLogs = useMemo(() => {
    const from = draft.date_from ? new Date(`${draft.date_from}T00:00:00`) : null
    const to = draft.date_to ? new Date(`${draft.date_to}T23:59:59`) : null
    return (logs || []).filter((log) => {
      if (draft.action && log.action !== draft.action) return false
      const createdAt = log.created_at ? new Date(log.created_at) : null
      if (from && createdAt && createdAt < from) return false
      if (to && createdAt && createdAt > to) return false
      return true
    })
  }, [logs, draft.action, draft.date_from, draft.date_to])

  const visibleLogs = filteredLogs.slice(0, visibleCount)

  return (
    <section className="admin-page">
      <h2 className="page-title">{t('nav.auditLogs')}</h2>
      <p className="muted">{t('auditLogs.adminView')}</p>

      <form className="filters" onSubmit={applyFilters}>
        <label className="field">
          <span>{t('auditLogs.categoryFilter')}</span>
          <select value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })}>
            <option value="operational">{t('auditLogs.categoryOperational')}</option>
            <option value="auth">{t('auditLogs.categoryAuth')}</option>
            <option value="all">{t('auditLogs.categoryAll')}</option>
          </select>
        </label>
        <label className="field">
          <span>{t('auditLogs.entityTypeFilter')}</span>
          <input
            value={draft.entity_type}
            onChange={(e) => setDraft({ ...draft, entity_type: e.target.value })}
            placeholder={t('auditLogs.entityPlaceholder')}
          />
        </label>
        <label className="field">
          <span>{t('auditLogs.entityId')}</span>
          <input
            value={draft.entity_id}
            onChange={(e) => setDraft({ ...draft, entity_id: e.target.value })}
            placeholder={t('auditLogs.uuidPlaceholder')}
          />
        </label>
        <label className="field">
          <span>{t('auditLogs.actorId')}</span>
          <input
            value={draft.actor_user_id}
            onChange={(e) => setDraft({ ...draft, actor_user_id: e.target.value })}
            placeholder={t('auditLogs.uuidPlaceholder')}
          />
        </label>
        <label className="field">
          <span>{t('auditLogs.actionFilter')}</span>
          <select
            value={draft.action}
            onChange={(e) => setDraft({ ...draft, action: e.target.value })}
          >
            <option value="">{t('auditLogs.allActions')}</option>
            {actionOptions.map((action) => (
              <option key={action} value={action}>
                {actionLabel(t, action)}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>{t('auditLogs.dateFrom')}</span>
          <input
            type="date"
            value={draft.date_from}
            onChange={(e) => setDraft({ ...draft, date_from: e.target.value })}
          />
        </label>
        <label className="field">
          <span>{t('auditLogs.dateTo')}</span>
          <input
            type="date"
            value={draft.date_to}
            onChange={(e) => setDraft({ ...draft, date_to: e.target.value })}
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
      {copiedId && <p className="grade-summary">{t('auditLogs.copiedId')}</p>}
      {!error && logs && filteredLogs.length === 0 && <Empty message={t('auditLogs.empty')} />}
      {!error && logs && filteredLogs.length > 0 && (
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
              {visibleLogs.map((log) => {
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
                      <td title={log.action}>{actionLabel(t, log.action)}</td>
                      <td className="nowrap">{log.entity_type}</td>
                      <td>
                        <button
                          type="button"
                          className="audit-id audit-id-button"
                          title={log.entity_id}
                          onClick={() => copyEntityId(log.entity_id)}
                        >
                          {log.entity_id}
                        </button>
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
          {filteredLogs.length > visibleLogs.length && (
            <button
              type="button"
              className="btn btn-ghost show-more-btn"
              onClick={() => setVisibleCount((count) => count + 25)}
            >
              {t('common.showMore', { count: Math.min(25, filteredLogs.length - visibleLogs.length) })}
            </button>
          )}
        </div>
      )}
    </section>
  )
}
