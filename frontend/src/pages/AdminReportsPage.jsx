import { useCallback, useEffect, useMemo, useState } from 'react'
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
  draft: 'parents cannot see it yet',
  approved: 'parents can see it',
  sent: 'parents can see it and were notified',
}

const NEEDS_REVIEW_COPY =
  'grades changed after approval/sending; admin must regenerate and approve again'

function ReportStatus({ report }) {
  if (report.needs_review) {
    const previousStatus =
      report.status === 'sent' ? 'Previously sent' : 'Previously approved'
    return (
      <div className="report-status-cell">
        <span className="badge badge-review" title={NEEDS_REVIEW_COPY}>
          Needs review
        </span>
        {(report.status === 'approved' || report.status === 'sent') && (
          <span className="status-secondary">{previousStatus}</span>
        )}
      </div>
    )
  }

  return (
    <div className="report-status-cell">
      <span title={STATUS_HELP[report.status] || report.status}>
        <StatusBadge status={report.status} />
      </span>
    </div>
  )
}

export default function AdminReportsPage() {
  const [reports, setReports] = useState(null)
  const [error, setError] = useState(null)
  const [statusFilter, setStatusFilter] = useState('all')
  const [needsReviewOnly, setNeedsReviewOnly] = useState(false)

  const refreshReports = useCallback(async () => {
    try {
      const data = await listReports()
      setReports(data)
      setError(null)
    } catch (err) {
      setError(err.message)
    }
  }, [])

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

  useEffect(() => {
    function refreshWhenVisible() {
      if (document.visibilityState === 'visible') {
        refreshReports()
      }
    }

    window.addEventListener('focus', refreshReports)
    document.addEventListener('visibilitychange', refreshWhenVisible)
    return () => {
      window.removeEventListener('focus', refreshReports)
      document.removeEventListener('visibilitychange', refreshWhenVisible)
    }
  }, [refreshReports])

  const filtered = useMemo(() => {
    if (!reports) return []
    return reports.filter((report) => {
      if (statusFilter !== 'all' && report.status !== statusFilter) return false
      if (needsReviewOnly && !report.needs_review) return false
      return true
    })
  }, [reports, statusFilter, needsReviewOnly])

  return (
    <section className="admin-page">
      <h2 className="page-title">Reports</h2>
      <p className="muted">Reports needing review appear first, then newest reports.</p>

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
            <label className="filter-check">
              <input
                type="checkbox"
                checked={needsReviewOnly}
                onChange={(e) => setNeedsReviewOnly(e.target.checked)}
              />
              <span>Needs review only</span>
            </label>
          </div>
          <div className="status-help" aria-label="Report status meanings">
            {Object.entries(STATUS_HELP).map(([status, help]) => (
              <span key={status} className="status-help-item">
                <StatusBadge status={status} /> {help}
              </span>
            ))}
            <span className="status-help-item">
              <span className="badge badge-review">Needs review</span> {NEEDS_REVIEW_COPY}
            </span>
          </div>

          {filtered.length === 0 ? (
            <Empty message="No reports match this filter." />
          ) : (
            <div className="table-scroll reports-table-scroll">
              <table className="table reports-table">
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
                        <ReportStatus report={report} />
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
