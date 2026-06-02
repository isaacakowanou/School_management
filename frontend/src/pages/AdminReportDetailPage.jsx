import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  approveReport,
  downloadReportPdf,
  getReport,
  sendReport,
  updateReportSummary,
} from '../api/reports.js'
import { checkReport, generateReportSummary } from '../api/ai.js'
import { formatGpa, formatPercent } from '../utils/format.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'
import StatusBadge from '../components/StatusBadge.jsx'

export default function AdminReportDetailPage() {
  const { reportId } = useParams()

  const [report, setReport] = useState(null)
  const [error, setError] = useState(null)

  const [warnings, setWarnings] = useState(null)
  const [summaryDraft, setSummaryDraft] = useState('')

  // Which action is in flight (e.g. 'check', 'summary', 'save', 'approve', 'send', 'pdf').
  const [pending, setPending] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [actionMessage, setActionMessage] = useState(null)

  const loadReport = useCallback(async () => {
    const data = await getReport(reportId)
    setReport(data)
    setSummaryDraft(data.ai_summary ?? '')
    return data
  }, [reportId])

  useEffect(() => {
    let cancelled = false
    setError(null)
    setReport(null)
    setWarnings(null)
    setActionError(null)
    setActionMessage(null)
    getReport(reportId)
      .then((data) => {
        if (cancelled) return
        setReport(data)
        setSummaryDraft(data.ai_summary ?? '')
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [reportId])

  // Run an action, surface a readable error, and refresh the report on success.
  async function runAction(name, fn, { refresh = true, successMessage = null } = {}) {
    setPending(name)
    setActionError(null)
    setActionMessage(null)
    try {
      const result = await fn()
      if (refresh) await loadReport()
      if (successMessage) setActionMessage(successMessage)
      return result
    } catch (err) {
      setActionError(err.message || 'Action failed.')
      return null
    } finally {
      setPending(null)
    }
  }

  async function handleCheck() {
    const result = await runAction('check', () => checkReport(reportId), {
      refresh: false,
    })
    if (result) {
      setWarnings(result)
      setActionMessage(
        result.length === 0
          ? 'Checker found no issues.'
          : `Checker found ${result.length} warning${result.length === 1 ? '' : 's'}.`,
      )
    }
  }

  async function handleGenerateSummary() {
    await runAction('summary', () => generateReportSummary(reportId), {
      successMessage: 'AI summary generated.',
    })
  }

  async function handleSaveSummary() {
    await runAction('save', () => updateReportSummary(reportId, summaryDraft), {
      successMessage: 'Summary saved.',
    })
  }

  async function handleApprove() {
    await runAction('approve', () => approveReport(reportId), {
      successMessage: 'Report approved.',
    })
  }

  async function handleSend() {
    const result = await runAction('send', () => sendReport(reportId), {
      successMessage: 'Report sent to parents.',
    })
    if (result) {
      setActionMessage(
        `Report sent · ${result.sent_count} delivered${
          result.failed_count ? ` · ${result.failed_count} failed` : ''
        }.`,
      )
    }
  }

  async function handleDownload() {
    await runAction(
      'pdf',
      async () => {
        const blob = await downloadReportPdf(reportId)
        const url = URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.download = `report-${report?.term ?? 'card'}-${report?.school_year ?? ''}.pdf`
          .replace(/\s+/g, '-')
          .toLowerCase()
        document.body.appendChild(link)
        link.click()
        link.remove()
        URL.revokeObjectURL(url)
        return true
      },
      { refresh: false },
    )
  }

  if (error) {
    return (
      <section className="admin-page">
        <Link to="/admin/reports" className="back-link">
          ← Reports
        </Link>
        <ErrorBanner message={error} />
      </section>
    )
  }

  if (!report) {
    return (
      <section className="admin-page">
        <Spinner label="Loading report…" />
      </section>
    )
  }

  const isDraft = report.status === 'draft'
  const isApproved = report.status === 'approved'
  const isSent = report.status === 'sent'
  const busy = pending !== null

  return (
    <section className="admin-page">
      <Link to="/admin/reports" className="back-link">
        ← Reports
      </Link>

      <div className="report-header">
        <div>
          <h2 className="page-title">Report card</h2>
          <p className="muted">
            {report.term} · {report.school_year} · <StatusBadge status={report.status} />
          </p>
          <p className="muted">
            Student ID: <span className="mono">{report.student_id}</span>
          </p>
        </div>
      </div>

      <div className="summary-row">
        <div className="stat">
          <div className="stat-label">Overall average</div>
          <div className="stat-value">{formatPercent(report.overall_average)}</div>
        </div>
        <div className="stat">
          <div className="stat-label">GPA</div>
          <div className="stat-value">{formatGpa(report.gpa)}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Status</div>
          <div className="stat-value" style={{ fontSize: '1.1rem' }}>
            <StatusBadge status={report.status} />
          </div>
        </div>
      </div>

      {/* ---- Workflow actions ---- */}
      <h3 className="section-title">Actions</h3>
      <div className="grade-actions">
        {isDraft && (
          <>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={handleCheck}
              disabled={busy}
            >
              {pending === 'check' ? 'Running checker…' : 'Run checker'}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={handleGenerateSummary}
              disabled={busy}
            >
              {pending === 'summary' ? 'Generating…' : 'Generate AI summary'}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleApprove}
              disabled={busy}
            >
              {pending === 'approve' ? 'Approving…' : 'Approve report'}
            </button>
          </>
        )}

        {isApproved && (
          <button type="button" className="btn btn-primary" onClick={handleSend} disabled={busy}>
            {pending === 'send' ? 'Sending…' : 'Send report'}
          </button>
        )}

        {(isApproved || isSent) && (
          <button type="button" className="btn btn-ghost" onClick={handleDownload} disabled={busy}>
            {pending === 'pdf' ? 'Preparing…' : 'Download PDF'}
          </button>
        )}
      </div>

      {actionMessage && <p className="grade-summary">{actionMessage}</p>}
      {actionError && <ErrorBanner message={actionError} />}

      {/* ---- AI warnings from checker ---- */}
      {warnings && warnings.length > 0 && (
        <>
          <h3 className="section-title">Checker warnings</h3>
          <ul className="card-list">
            {warnings.map((w, i) => (
              <li key={i} className="card">
                <div className="report-row">
                  <span className="report-term">{w.warning_type}</span>
                  <span className={`badge badge-${w.severity === 'high' ? 'sent' : 'approved'}`}>
                    {w.severity}
                  </span>
                </div>
                <div className="muted">{w.message}</div>
              </li>
            ))}
          </ul>
        </>
      )}

      {/* ---- Courses ---- */}
      <h3 className="section-title">Courses</h3>
      {report.courses.length === 0 ? (
        <Empty message="This report has no course rows." />
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Course</th>
              <th className="num">Average</th>
              <th className="num">Grade</th>
            </tr>
          </thead>
          <tbody>
            {report.courses.map((course) => (
              <tr key={course.id}>
                <td>{course.course_name}</td>
                <td className="num">{formatPercent(course.average)}</td>
                <td className="num">{course.letter_grade}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* ---- AI summary ---- */}
      <h3 className="section-title">Parent summary</h3>
      {isDraft ? (
        <div>
          <textarea
            className="field"
            style={{ width: '100%', minHeight: 140, padding: '10px 12px' }}
            value={summaryDraft}
            onChange={(e) => setSummaryDraft(e.target.value)}
            placeholder="Generate a summary above, or write one here…"
            disabled={busy}
          />
          <div className="grade-actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleSaveSummary}
              disabled={busy}
            >
              {pending === 'save' ? 'Saving…' : 'Save summary'}
            </button>
          </div>
        </div>
      ) : report.ai_summary ? (
        <div className="card summary-card">{report.ai_summary}</div>
      ) : (
        <Empty message="No summary was set for this report." />
      )}
    </section>
  )
}
