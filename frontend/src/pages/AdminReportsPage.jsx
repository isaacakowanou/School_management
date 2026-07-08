import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { listReports } from '../api/reports.js'
import { formatReportAverage } from '../utils/format.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'
import StatusBadge from '../components/StatusBadge.jsx'

const STATUS_KEYS = ['all', 'draft', 'approved', 'sent']

const STATUS_HELP_KEYS = ['draft', 'approved', 'sent']

function ReportStatus({ report, t }) {
  if (report.needs_review) {
    const previousStatus =
      report.status === 'sent' ? t('reports.previouslySent') : t('reports.previouslyApproved')
    return (
      <div className="report-status-cell">
        <span className="badge badge-review" title={t('reports.needsReviewCopy')}>
          {t('reports.needsReview')}
        </span>
        {(report.status === 'approved' || report.status === 'sent') && (
          <span className="status-secondary">{previousStatus}</span>
        )}
      </div>
    )
  }

  return (
    <div className="report-status-cell">
      <span title={t(`reports.statusHelp${report.status.charAt(0).toUpperCase() + report.status.slice(1)}`) || report.status}>
        <StatusBadge status={report.status} />
      </span>
    </div>
  )
}

export default function AdminReportsPage() {
  const { t } = useTranslation()
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

  const statusLabel = (key) => {
    const map = {
      all: t('reports.statusAll'),
      draft: t('reports.statusDraft'),
      approved: t('reports.statusApproved'),
      sent: t('reports.statusSent'),
    }
    return map[key] ?? key
  }

  const statusHelpText = (key) => {
    const map = {
      draft: t('reports.statusHelpDraft'),
      approved: t('reports.statusHelpApproved'),
      sent: t('reports.statusHelpSent'),
    }
    return map[key] ?? ''
  }

  return (
    <section className="admin-page">
      <div className="report-header">
        <div>
          <h2 className="page-title">{t('nav.reports')}</h2>
          <p className="muted">{t('reports.subtitle')}</p>
        </div>
        <Link to="/admin/reports/class" className="btn btn-primary">
          {t('classReports.title')}
        </Link>
      </div>

      {error && <ErrorBanner message={error} />}
      {!error && reports === null && <Spinner label={t('reports.loading')} />}

      {!error && reports && (
        <>
          <div className="filters">
            <label className="field">
              <span>{t('common.status')}</span>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="grade-input"
                style={{ width: 'auto', textAlign: 'left' }}
              >
                {STATUS_KEYS.map((key) => (
                  <option key={key} value={key}>
                    {statusLabel(key)}
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
              <span>{t('reports.needsReviewOnly')}</span>
            </label>
          </div>
          <div className="status-help" aria-label="Report status meanings">
            {STATUS_HELP_KEYS.map((key) => (
              <span key={key} className="status-help-item">
                <StatusBadge status={key} /> {statusHelpText(key)}
              </span>
            ))}
            <span className="status-help-item">
              <span className="badge badge-review">{t('reports.needsReview')}</span> {t('reports.needsReviewCopy')}
            </span>
          </div>

          {filtered.length === 0 ? (
            <Empty message={t('reports.empty')} />
          ) : (
            <div className="table-scroll reports-table-scroll">
              <table className="table reports-table">
                <thead>
                  <tr>
                    <th>{t('reports.student')}</th>
                    <th>{t('reports.term')}</th>
                    <th>{t('reports.schoolYear')}</th>
                    <th>{t('common.status')}</th>
                    <th className="num">{t('reports.average')}</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((report) => (
                    <tr key={report.id}>
                      <td>
                        <div className="student-cell-main">
                          {report.student_name || t('reports.unknownStudent')}
                        </div>
                        <div className="student-cell-meta">
                          #{report.student_number || report.student_id}
                        </div>
                      </td>
                      <td className="nowrap">{report.term}</td>
                      <td className="nowrap">{report.school_year}</td>
                      <td>
                        <ReportStatus report={report} t={t} />
                      </td>
                      <td className="num">{formatReportAverage(report.bilingual_average ?? report.overall_average, report.scale)}</td>
                      <td className="nowrap">
                        <Link className="back-link" to={`/admin/reports/${report.id}`}>
                          {t('common.open')}
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
