import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  approveReport,
  downloadReportPdf,
  getAdminReport,
  getReportStaleness,
  regenerateReport,
  sendReport,
  updateReportDetails,
  updateReportSummary,
} from '../api/reports.js'
import { checkReport, generateReportSummary } from '../api/ai.js'
import { formatReportAverage, formatScore20 } from '../utils/format.js'
import ReportAverages from '../components/ReportAverages.jsx'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import { LETTER_GRADES } from '../constants/letterGrades.js'

const COMMENT_FIELDS = [
  ['teacher_comment_fr', "Teacher's Comment / Commentaire du censeur (FR)"],
  ['teacher_comment_en', "Teacher's Comment / Commentaire du censeur (EN)"],
  ['principal_comment_fr', "Principal's Comment / Commentaire du directeur (FR)"],
  ['principal_comment_en', "Principal's Comment / Commentaire du directeur (EN)"],
]

const EMPTY_COMMENTS = {
  teacher_comment_fr: '',
  teacher_comment_en: '',
  principal_comment_fr: '',
  principal_comment_en: '',
}

function hasValue(value) {
  return value !== null && value !== undefined
}

function itemGrades(items, grades) {
  return Object.fromEntries((items ?? []).map((item) => [item.item_key, grades[item.item_key] || '']))
}

function storedItemGrades(items) {
  return Object.fromEntries((items ?? []).map((item) => [item.item_key, item.letter_grade ?? '']))
}

export default function AdminReportDetailPage() {
  const { reportId } = useParams()
  const { t } = useTranslation()

  const [report, setReport] = useState(null)
  const [error, setError] = useState(null)
  const [staleness, setStaleness] = useState(null)
  const [stalenessError, setStalenessError] = useState(null)

  const [warnings, setWarnings] = useState(null)
  const [summaryDraft, setSummaryDraft] = useState('')
  const [conductGrades, setConductGrades] = useState({})
  const [workHabitGrades, setWorkHabitGrades] = useState({})
  const [comments, setComments] = useState(EMPTY_COMMENTS)

  // Which action is in flight (e.g. 'check', 'summary', 'save', 'approve', 'send', 'pdf').
  const [pending, setPending] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [actionMessage, setActionMessage] = useState(null)

  const loadReport = useCallback(async () => {
    const data = await getAdminReport(reportId)
    setReport(data)
    setSummaryDraft(data.ai_summary ?? '')
    return data
  }, [reportId])

  const loadStaleness = useCallback(async () => {
    try {
      const data = await getReportStaleness(reportId)
      setStaleness(data)
      setStalenessError(null)
      return data
    } catch {
      setStaleness(null)
      setStalenessError(t('reports.stalenessUnavailable'))
      return null
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reportId])

  const refreshReportView = useCallback(async () => {
    const data = await loadReport()
    await loadStaleness()
    return data
  }, [loadReport, loadStaleness])

  // Seed the editable conduct / work-habit / comment drafts whenever a fresh
  // report loads (initial load or a post-action refresh).
  useEffect(() => {
    if (!report) return
    setConductGrades(
      Object.fromEntries((report.conduct_items ?? []).map((i) => [i.item_key, i.letter_grade ?? ''])),
    )
    setWorkHabitGrades(
      Object.fromEntries((report.work_habit_items ?? []).map((i) => [i.item_key, i.letter_grade ?? ''])),
    )
    setComments({
      teacher_comment_fr: report.teacher_comment_fr ?? '',
      teacher_comment_en: report.teacher_comment_en ?? '',
      principal_comment_fr: report.principal_comment_fr ?? '',
      principal_comment_en: report.principal_comment_en ?? '',
    })
  }, [report])

  useEffect(() => {
    let cancelled = false
    setError(null)
    setReport(null)
    setStaleness(null)
    setStalenessError(null)
    setWarnings(null)
    setActionError(null)
    setActionMessage(null)

    async function load() {
      try {
        const data = await getAdminReport(reportId)
        if (cancelled) return
        setReport(data)
        setSummaryDraft(data.ai_summary ?? '')
      } catch (err) {
        if (!cancelled) setError(err.message)
        return
      }

      try {
        const data = await getReportStaleness(reportId)
        if (cancelled) return
        setStaleness(data)
        setStalenessError(null)
      } catch {
        if (!cancelled) {
          setStaleness(null)
          setStalenessError(t('reports.stalenessUnavailable'))
        }
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [reportId])

  useEffect(() => {
    function refreshWhenVisible() {
      if (document.visibilityState === 'visible') {
        loadStaleness()
      }
    }

    window.addEventListener('focus', loadStaleness)
    document.addEventListener('visibilitychange', refreshWhenVisible)
    return () => {
      window.removeEventListener('focus', loadStaleness)
      document.removeEventListener('visibilitychange', refreshWhenVisible)
    }
  }, [loadStaleness])

  useEffect(() => {
    if (!report) return undefined
    const current = {
      conduct: itemGrades(report.conduct_items, conductGrades),
      workHabits: itemGrades(report.work_habit_items, workHabitGrades),
      comments,
      summary: summaryDraft,
    }
    const stored = {
      conduct: storedItemGrades(report.conduct_items),
      workHabits: storedItemGrades(report.work_habit_items),
      comments: {
        teacher_comment_fr: report.teacher_comment_fr ?? '',
        teacher_comment_en: report.teacher_comment_en ?? '',
        principal_comment_fr: report.principal_comment_fr ?? '',
        principal_comment_en: report.principal_comment_en ?? '',
      },
      summary: report.ai_summary ?? '',
    }
    if (JSON.stringify(current) === JSON.stringify(stored)) return undefined

    function handleBeforeUnload(event) {
      event.preventDefault()
      event.returnValue = ''
    }

    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [report, conductGrades, workHabitGrades, comments, summaryDraft])

  // Run an action, surface a readable error, and refresh the report on success.
  async function runAction(name, fn, { refresh = true, successMessage = null } = {}) {
    setPending(name)
    setActionError(null)
    setActionMessage(null)
    try {
      const result = await fn()
      if (refresh) await refreshReportView()
      if (successMessage) setActionMessage(successMessage)
      return result
    } catch (err) {
      setActionError(err.message || t('common.actionFailed'))
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
          ? t('reports.checkerNoIssues')
          : t('reports.checkerResult', { count: result.length }),
      )
    }
  }

  async function handleGenerateSummary() {
    await runAction('summary', () => generateReportSummary(reportId), {
      successMessage: t('reports.summaryGenerated'),
    })
  }

  async function handleSaveSummary() {
    await runAction('save', () => updateReportSummary(reportId, summaryDraft), {
      successMessage: t('reports.summarySaved'),
    })
  }

  async function handleSaveDetails() {
    const payload = {
      conduct_items: (report.conduct_items ?? []).map((item) => ({
        item_key: item.item_key,
        letter_grade: conductGrades[item.item_key] || null,
      })),
      work_habit_items: (report.work_habit_items ?? []).map((item) => ({
        item_key: item.item_key,
        letter_grade: workHabitGrades[item.item_key] || null,
      })),
      teacher_comment_fr: comments.teacher_comment_fr.trim() || null,
      teacher_comment_en: comments.teacher_comment_en.trim() || null,
      principal_comment_fr: comments.principal_comment_fr.trim() || null,
      principal_comment_en: comments.principal_comment_en.trim() || null,
    }
    await runAction('details', () => updateReportDetails(reportId, payload), {
      successMessage: t('reports.detailsSaved'),
    })
  }

  async function handleApprove() {
    await runAction('approve', () => approveReport(reportId), {
      successMessage: t('reports.reportApproved'),
    })
  }

  async function handleSend() {
    const isResend = report?.status === 'sent'
    if (isResend && !window.confirm(t('reports.confirmResend'))) {
      return
    }

    const result = await runAction('send', () => sendReport(reportId), {
      successMessage: isResend ? t('reports.reportResent') : t('reports.reportSent'),
    })
    if (result) {
      const statusLabel = isResend ? t('reports.reportResent') : t('reports.reportSent')
      const failedPart = result.failed_count ? ` · ${result.failed_count} ${t('reports.failed')}` : ''
      setActionMessage(`${statusLabel} · ${result.sent_count} ${t('reports.delivered')}${failedPart}`)
    }
  }

  async function handleRegenerate() {
    await runAction('regenerate', () => regenerateReport(reportId), {
      successMessage: t('reports.regenerated'),
    })
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
          ← {t('nav.reports')}
        </Link>
        <ErrorBanner message={error} />
      </section>
    )
  }

  if (!report) {
    return (
      <section className="admin-page">
        <Spinner label={t('reports.loadingOne')} />
      </section>
    )
  }

  const isDraft = report.status === 'draft'
  const isApproved = report.status === 'approved'
  const isSent = report.status === 'sent'
  const busy = pending !== null
  const summaryDirty = summaryDraft !== (report.ai_summary ?? '')
  const detailsDirty = (() => {
    const current = {
      conduct: itemGrades(report.conduct_items, conductGrades),
      workHabits: itemGrades(report.work_habit_items, workHabitGrades),
      comments,
    }
    const stored = {
      conduct: storedItemGrades(report.conduct_items),
      workHabits: storedItemGrades(report.work_habit_items),
      comments: {
        teacher_comment_fr: report.teacher_comment_fr ?? '',
        teacher_comment_en: report.teacher_comment_en ?? '',
        principal_comment_fr: report.principal_comment_fr ?? '',
        principal_comment_en: report.principal_comment_en ?? '',
      },
    }
    return JSON.stringify(current) !== JSON.stringify(stored)
  })()
  const hasUnsavedChanges = summaryDirty || detailsDirty
  const staleReason = staleness?.reason
    ? staleness.reason.includes('could not be built')
      ? t('reports.staleReasonIncomplete')
      : staleness.reason.includes('course set changed')
        ? t('reports.staleReasonCourseSet')
        : t('reports.staleReasonGeneric')
    : null
  const studentName = report.student_name || t('reports.unknownStudent')
  const studentNumber = report.student_number || report.student_id

  return (
    <section className="admin-page">
      <Link to="/admin/reports" className="back-link">
        ← {t('nav.reports')}
      </Link>

      <div className="report-header">
        <div>
          <h2 className="page-title">{t('reports.reportCard')}</h2>
          <p className="muted">
            {report.term} · {report.school_year} · <StatusBadge status={report.status} />
          </p>
          <p className="muted">
            {t('reports.student')}: <strong>{studentName}</strong>
          </p>
          <p className="muted">
            {t('reports.studentNumber')}: <span className="mono">{studentNumber}</span>
          </p>
        </div>
      </div>

      <div className="summary-row">
        <ReportAverages report={report} />
        <div className="stat">
          <div className="stat-label">{t('common.status')}</div>
          <div className="stat-value stat-value-compact">
            <StatusBadge status={report.status} />
          </div>
        </div>
      </div>

      {(isApproved || isSent) && (
        <div className="state state-warning" role="status">
          {t('reports.approvedSentEditWarning')}
        </div>
      )}

      <div className="report-sticky-actions">
        <button
          type="button"
          className="btn btn-primary"
          onClick={handleSaveDetails}
          disabled={busy || !detailsDirty}
        >
          {pending === 'details' ? t('common.saving') : t('reports.saveDetails')}
        </button>
        <button
          type="button"
          className="btn btn-primary"
          onClick={handleSaveSummary}
          disabled={busy || !summaryDirty}
        >
          {pending === 'save' ? t('common.saving') : t('reports.saveSummary')}
        </button>
        {isDraft && (
          <>
            <button type="button" className="btn btn-ghost" onClick={handleCheck} disabled={busy}>
              {pending === 'check' ? t('reports.checking') : t('reports.check')}
            </button>
            <button type="button" className="btn btn-ghost" onClick={handleGenerateSummary} disabled={busy}>
              {pending === 'summary' ? t('reports.generating') : t('reports.generateSummary')}
            </button>
            <button type="button" className="btn btn-ghost" onClick={handleApprove} disabled={busy || hasUnsavedChanges}>
              {pending === 'approve' ? t('reports.approving') : t('reports.approve')}
            </button>
          </>
        )}
        {(isApproved || isSent) && (
          <button type="button" className="btn btn-ghost" onClick={handleSend} disabled={busy || hasUnsavedChanges}>
            {pending === 'send'
              ? isSent
                ? t('reports.resending')
                : t('reports.sending')
              : isSent
                ? t('reports.resend')
                : t('reports.send')}
          </button>
        )}
        {(isApproved || isSent) && (
          <button type="button" className="btn btn-ghost" onClick={handleDownload} disabled={busy || hasUnsavedChanges}>
            {pending === 'pdf' ? t('reports.preparing') : t('reports.downloadPdf')}
          </button>
        )}
      </div>

      {staleness?.is_stale && (
        <section className="stale-report-warning" aria-live="polite">
          <div>
            <h3>{t('reports.gradesChanged')}</h3>
            <p>{t('reports.gradesChangedDesc')}</p>
            {staleReason && <p className="muted">{staleReason}</p>}
          </div>

          <div className="stale-report-values" aria-label="Snapshot and current values">
            <div>
              <span>{t('reports.snapshotAvg')}</span>
              <strong>{formatReportAverage(staleness.snapshot_overall_average, report.scale)}</strong>
            </div>
            <div>
              <span>{t('reports.currentAvg')}</span>
              <strong>
                {hasValue(staleness.current_overall_average)
                  ? formatScore20(staleness.current_overall_average)
                  : t('reports.unavailable')}
              </strong>
            </div>
          </div>

          <button
            type="button"
            className="btn btn-primary"
            onClick={handleRegenerate}
            disabled={busy}
          >
            {pending === 'regenerate' ? t('reports.regenerating') : t('reports.regenerate')}
          </button>
        </section>
      )}

      {actionMessage && <p className="grade-summary">{actionMessage}</p>}
      {actionError && <ErrorBanner message={actionError} />}
      {stalenessError && <p className="grade-summary grade-summary-warn">{stalenessError}</p>}

      {/* ---- AI warnings from checker ---- */}
      {warnings && warnings.length > 0 && (
        <>
          <h3 className="section-title">{t('reports.checkerWarningsSection')}</h3>
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
      <h3 className="section-title">{t('reports.coursesSection')}</h3>
      {report.courses.length === 0 ? (
        <Empty message={t('reports.noCourseRows')} />
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t('reports.course')}</th>
              <th className="num">{t('reports.average')}</th>
              <th className="num">{t('reports.grade')}</th>
            </tr>
          </thead>
          <tbody>
            {report.courses.map((course) => (
              <tr key={course.id}>
                <td>{course.course_name}</td>
                <td className="num">{formatReportAverage(course.average, report.scale)}</td>
                <td className="num">{course.letter_grade}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* ---- Conduct ---- */}
      <h3 className="section-title">{t('reports.conductSection')}</h3>
      <table className="table">
        <thead>
          <tr>
            <th>{t('reports.item')}</th>
            <th className="num">{t('reports.grade')}</th>
          </tr>
        </thead>
        <tbody>
          {(report.conduct_items ?? []).map((item) => (
            <tr key={item.item_key}>
              <td>
                {item.label_en} <span className="muted">/ {item.label_fr}</span>
              </td>
              <td className="num">
                <select
                  className="grade-input"
                  value={conductGrades[item.item_key] ?? ''}
                  onChange={(e) => setConductGrades((g) => ({ ...g, [item.item_key]: e.target.value }))}
                  disabled={busy}
                >
                  <option value="">—</option>
                  {LETTER_GRADES.map((grade) => (
                    <option key={grade} value={grade}>
                      {grade}
                    </option>
                  ))}
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* ---- Work habits ---- */}
      <h3 className="section-title">{t('reports.workHabitsSection')}</h3>
      <table className="table">
        <thead>
          <tr>
            <th>{t('reports.item')}</th>
            <th className="num">{t('reports.grade')}</th>
          </tr>
        </thead>
        <tbody>
          {(report.work_habit_items ?? []).map((item) => (
            <tr key={item.item_key}>
              <td>
                {item.label_en} <span className="muted">/ {item.label_fr}</span>
              </td>
              <td className="num">
                <select
                  className="grade-input"
                  value={workHabitGrades[item.item_key] ?? ''}
                  onChange={(e) => setWorkHabitGrades((g) => ({ ...g, [item.item_key]: e.target.value }))}
                  disabled={busy}
                >
                  <option value="">—</option>
                  {LETTER_GRADES.map((grade) => (
                    <option key={grade} value={grade}>
                      {grade}
                    </option>
                  ))}
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* ---- Conduct / work-habit comments ---- */}
      <h3 className="section-title">{t('reports.commentsSection')}</h3>
      {COMMENT_FIELDS.map(([field, label]) => (
        <label className="field" key={field}>
          <span>{label}</span>
          <textarea
            className="textarea-field"
            value={comments[field]}
            onChange={(e) => setComments((c) => ({ ...c, [field]: e.target.value }))}
            disabled={busy}
          />
        </label>
      ))}
      <div className="grade-actions">
        <button type="button" className="btn btn-primary" onClick={handleSaveDetails} disabled={busy}>
          {pending === 'details' ? t('common.saving') : t('reports.saveDetails')}
        </button>
      </div>

      {/* ---- AI summary ---- */}
      <h3 className="section-title">{t('reports.parentSummarySection')}</h3>
      <div>
        <textarea
          className="textarea-field textarea-field-large"
          value={summaryDraft}
          onChange={(e) => setSummaryDraft(e.target.value)}
          placeholder={t('reports.summaryPlaceholder')}
          disabled={busy}
        />
        <div className="grade-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleSaveSummary}
            disabled={busy}
          >
            {pending === 'save' ? t('common.saving') : t('reports.saveSummary')}
          </button>
        </div>
      </div>
    </section>
  )
}
