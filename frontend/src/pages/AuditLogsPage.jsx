import { Fragment, useEffect, useState } from 'react'
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

export default function AuditLogsPage() {
  const [draft, setDraft] = useState(EMPTY_FILTERS) // form inputs
  const [filters, setFilters] = useState(EMPTY_FILTERS) // applied filters (drives fetch)
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
      <h2 className="page-title">Audit logs</h2>
      <p className="muted">Administrator view</p>

      <form className="filters" onSubmit={applyFilters}>
        <label className="field">
          <span>Entity type</span>
          <input
            value={draft.entity_type}
            onChange={(e) => setDraft({ ...draft, entity_type: e.target.value })}
            placeholder="e.g. report_card"
          />
        </label>
        <label className="field">
          <span>Entity ID</span>
          <input
            value={draft.entity_id}
            onChange={(e) => setDraft({ ...draft, entity_id: e.target.value })}
            placeholder="UUID"
          />
        </label>
        <label className="field">
          <span>Actor user ID</span>
          <input
            value={draft.actor_user_id}
            onChange={(e) => setDraft({ ...draft, actor_user_id: e.target.value })}
            placeholder="UUID"
          />
        </label>
        <div className="filters-actions">
          <button type="submit" className="btn btn-primary">
            Apply
          </button>
          <button type="button" className="btn btn-ghost" onClick={clearFilters}>
            Clear
          </button>
        </div>
      </form>

      {error && <ErrorBanner message={error} />}
      {!error && logs === null && <Spinner label="Loading audit logs…" />}
      {!error && logs && logs.length === 0 && <Empty message="No audit log entries match." />}
      {!error && logs && logs.length > 0 && (
        <div className="table-scroll">
          <table className="table audit-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Entity type</th>
                <th>Entity ID</th>
                <th>Details</th>
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
                        <span className="audit-id" title={log.actor_user_id}>
                          {log.actor_user_id}
                        </span>
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
                          {isExpanded ? 'Hide details' : 'View details'}
                        </button>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr className="audit-details-row">
                        <td colSpan={6}>
                          <div className="audit-details-grid">
                            <div>
                              <h3>Old value</h3>
                              <pre className="json-cell json-cell-expanded">{oldValue}</pre>
                            </div>
                            <div>
                              <h3>New value</h3>
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
