import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { listReports } from '../api/reports.js'
import { formatGpa, formatPercent } from '../utils/format.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'
import StatusBadge from '../components/StatusBadge.jsx'

const STATUS_OPTIONS = [
  { value: 'all', label: 'All statuses' },
  { value: 'draft', label: 'Draft' },
  { value: 'approved', label: 'Approved' },
  { value: 'sent', label: 'Sent' },
]

const STATUS_HELP = {
  draft: 'not visible to parents yet',
  approved: 'visible to parents',
  sent: 'sent/notified',
}

export default function AdminReportsPage() {
  const [reports, setReports] = useState(null)
  const [error, setError] = useState(null)
  const [statusFilter, setStatusFilter] = useState('all')

  useEffect(() => {
    let cancelled = false
    setError(null)
    setReports(null)
    listReports()
      .then((data) => {
        if (!cancelled) setReports(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const filtered = useMemo(() => {
    if (!reports) return []
    if (statusFilter === 'all') return reports
    return reports.filter((r) => r.status === statusFilter)
  }, [reports, statusFilter])

  return (
    <section className="admin-page">
      <h2 className="page-title">Reports</h2>
      <p className="muted">All report cards across the school, newest first.</p>

      {error && <ErrorBanner message={error} />}
      {!error && reports === null && <Spinner label="Loading reports…" />}

      {!error && reports && (
        <>
          <div className="filters">
            <label className="field">
              <span>Status</span>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="grade-input"
                style={{ width: 'auto', textAlign: 'left' }}
              >
                {STATUS_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="status-help" aria-label="Report status meanings">
            {Object.entries(STATUS_HELP).map(([status, help]) => (
              <span key={status} className="status-help-item">
                <StatusBadge status={status} /> {help}
              </span>
            ))}
          </div>

          {filtered.length === 0 ? (
            <Empty message="No reports match this filter." />
          ) : (
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>Student</th>
                    <th>Term</th>
                    <th>School year</th>
                    <th>Status</th>
                    <th className="num">Average</th>
                    <th className="num">GPA</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((report) => (
                    <tr key={report.id}>
                      <td>
                        <div className="student-cell-main">
                          {report.student_name || 'Unknown student'}
                        </div>
                        <div className="student-cell-meta">
                          #{report.student_number || report.student_id}
                        </div>
                      </td>
                      <td className="nowrap">{report.term}</td>
                      <td className="nowrap">{report.school_year}</td>
                      <td>
                        <span title={STATUS_HELP[report.status] || report.status}>
                          <StatusBadge status={report.status} />
                        </span>
                      </td>
                      <td className="num">{formatPercent(report.overall_average)}</td>
                      <td className="num">{formatGpa(report.gpa)}</td>
                      <td className="nowrap">
                        <Link className="back-link" to={`/admin/reports/${report.id}`}>
                          Open →
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  )
}
