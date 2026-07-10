import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { listReports } from '../api/reports.js'
import { listClasses } from '../api/classes.js'
import { listStudents } from '../api/students.js'
import { formatReportAverage } from '../utils/format.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'
import StatusBadge from '../components/StatusBadge.jsx'

const STATUS_KEYS = ['all', 'draft', 'approved', 'sent', 'needs_review']

const STATUS_HELP_KEYS = ['draft', 'approved', 'sent']

function ReportStatus({ report, t }) {
  if (report.needs_review) {
    const previousStatus =
      report.status === 'sent'
        ? t('reports.previouslySent')
        : report.status === 'approved'
          ? t('reports.previouslyApproved')
          : null
    return (
      <div className="report-status-cell">
        <StatusBadge status="needs_review" />
        {previousStatus && (
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
  const [search, setSearch] = useState('')
  const [classFilter, setClassFilter] = useState('')
  const [classes, setClasses] = useState([])
  const [studentClassById, setStudentClassById] = useState(new Map())
  const [visibleCount, setVisibleCount] = useState(25)

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
    Promise.all([listReports(), listClasses().catch(() => []), listStudents().catch(() => [])])
      .then(([reportData, classData, studentData]) => {
        if (cancelled) return
        setReports(reportData)
        setClasses(classData)
        setStudentClassById(new Map(studentData.map((student) => [student.id, student.class_id || ''])))
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
      const query = search.trim().toLowerCase()
      const haystack = `${report.student_name || ''} ${report.student_number || ''}`.toLowerCase()
      if (query && !haystack.includes(query)) return false
      if (statusFilter === 'needs_review' && !report.needs_review) return false
      if (statusFilter !== 'all' && statusFilter !== 'needs_review' && report.status !== statusFilter) return false
      if (needsReviewOnly && !report.needs_review) return false
      if (classFilter && studentClassById.get(report.student_id) !== classFilter) return false
      return true
    })
  }, [reports, search, statusFilter, needsReviewOnly, classFilter, studentClassById])

  const visibleReports = filtered.slice(0, visibleCount)

  const statusLabel = (key) => {
    const map = {
      all: t('reports.statusAll'),
      draft: t('reports.statusDraft'),
      approved: t('reports.statusApproved'),
      sent: t('reports.statusSent'),
      needs_review: t('reports.needsReview'),
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
          <div className="list-toolbar">
            <label className="toolbar-field">
              <span>{t('common.search')}</span>
              <input
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value)
                  setVisibleCount(25)
                }}
                placeholder={t('reports.searchPlaceholder')}
              />
            </label>
            <label className="toolbar-field">
              <span>{t('common.status')}</span>
              <select
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value)
                  setVisibleCount(25)
                }}
              >
                {STATUS_KEYS.map((key) => (
                  <option key={key} value={key}>
                    {statusLabel(key)}
                  </option>
                ))}
              </select>
            </label>
            <label className="toolbar-field">
              <span>{t('reports.classFilter')}</span>
              <select
                value={classFilter}
                onChange={(event) => {
                  setClassFilter(event.target.value)
                  setVisibleCount(25)
                }}
              >
                <option value="">{t('common.all')}</option>
                {classes.map((cls) => (
                  <option key={cls.id} value={cls.id}>
                    {cls.name_fr}{cls.name_en ? ` (${cls.name_en})` : ''} · {cls.school_year}
                  </option>
                ))}
              </select>
            </label>
            <label className="filter-check">
              <input
                type="checkbox"
                checked={needsReviewOnly}
                onChange={(e) => {
                  setNeedsReviewOnly(e.target.checked)
                  setVisibleCount(25)
                }}
              />
              <span>{t('reports.needsReviewOnly')}</span>
            </label>
            <details className="status-popover">
              <summary aria-label={t('reports.statusLegend')}>?</summary>
              <div className="status-popover-panel">
                {STATUS_HELP_KEYS.map((key) => (
                  <span key={key} className="status-help-item">
                    <StatusBadge status={key} /> {statusHelpText(key)}
                  </span>
                ))}
                <span className="status-help-item">
                  <span className="badge badge-review">{t('reports.needsReview')}</span> {t('reports.needsReviewCopy')}
                </span>
              </div>
            </details>
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
                  {visibleReports.map((report) => (
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
                        <Link className="link-action" to={`/admin/reports/${report.id}`}>
                          {t('common.open')}
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {filtered.length > visibleReports.length && (
                <button
                  type="button"
                  className="btn btn-ghost show-more-btn"
                  onClick={() => setVisibleCount((count) => count + 25)}
                >
                  {t('common.showMore', { count: Math.min(25, filtered.length - visibleReports.length) })}
                </button>
              )}
            </div>
          )}
        </>
      )}
    </section>
  )
}
