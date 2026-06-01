import { useEffect, useState } from 'react'
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

  useEffect(() => {
    let cancelled = false
    setError(null)
    setLogs(null)
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

  return (
    <section>
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
                <th>Old value</th>
                <th>New value</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={log.id}>
                  <td className="nowrap">{formatTime(log.created_at)}</td>
                  <td className="mono">{log.actor_user_id}</td>
                  <td>{log.action}</td>
                  <td>{log.entity_type}</td>
                  <td className="mono">{log.entity_id}</td>
                  <td>
                    <pre className="json-cell">{formatJson(log.old_value)}</pre>
                  </td>
                  <td>
                    <pre className="json-cell">{formatJson(log.new_value)}</pre>
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
