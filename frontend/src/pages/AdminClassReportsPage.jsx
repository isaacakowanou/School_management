import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  batchApproveReports,
  batchGenerateReports,
  batchSendReports,
  createClassPdfJob,
  getClassReportStatus,
  pollClassPdfJob,
  regenerateReport,
} from '../api/reports.js'
import { listClasses } from '../api/classes.js'
import { formatReportAverage } from '../utils/format.js'
import ClassSelect from '../components/ClassSelect.jsx'
import TermSelect from '../components/TermSelect.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

export default function AdminClassReportsPage() {
  const { t } = useTranslation()
  const [classes, setClasses] = useState([])
  const [classId, setClassId] = useState('')
  const [term, setTerm] = useState('')
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [actionMessage, setActionMessage] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [runningAction, setRunningAction] = useState(null)
  const [regeneratingId, setRegeneratingId] = useState(null)
  const [downloadingPdf, setDownloadingPdf] = useState(false)

  useEffect(() => {
    let cancelled = false
    listClasses()
      .then((data) => {
        if (!cancelled) setClasses(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const selectedClass = useMemo(
    () => classes.find((item) => item.id === classId) || null,
    [classes, classId],
  )
  const schoolYear = selectedClass?.school_year || ''
  const batchArgs = useMemo(
    () => ({ classId, schoolYear, term }),
    [classId, schoolYear, term],
  )

  const loadStatus = useCallback(async () => {
    if (!classId || !term || !schoolYear) {
      setStatus(null)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const data = await getClassReportStatus({ classId, schoolYear, term })
      setStatus(data)
    } catch (err) {
      setError(err.message)
      setStatus(null)
    } finally {
      setLoading(false)
    }
  }, [classId, term, schoolYear])

  useEffect(() => {
    setActionMessage(null)
    setActionError(null)
    loadStatus()
  }, [loadStatus])

  // Students batch-generate would actually create reports for.
  const generatableCount = useMemo(
    () =>
      (status?.students || []).filter((row) => !row.report_id && row.results_count > 0 && row.missing_results_count === 0).length,
    [status],
  )
  const partialRows = useMemo(
    () => (status?.students || []).filter((row) => !row.report_id && row.missing_results_count > 0),
    [status],
  )
  const midTrimesterNoCompleteResults = !!(
    status
    && status.total_students > 0
    && status.students.some((row) => row.expected_results_count > 0)
    && status.students.every((row) => row.results_count === 0)
  )

  async function runBatch(kind) {
    setActionMessage(null)
    setActionError(null)

    const confirmText =
      kind === 'generate'
        ? t('classReports.confirmGenerate', { count: generatableCount })
        : kind === 'approve'
          ? t('classReports.confirmApprove', { count: status.draft_count })
          : t('classReports.confirmSend', { count: status.approved_count })
    if (!window.confirm(confirmText)) return

    let generatePartial = false
    if (kind === 'generate' && partialRows.length > 0) {
      generatePartial = window.confirm(
        t('classReports.confirmGeneratePartial', { count: partialRows.length }),
      )
    }

    setRunningAction(kind)
    try {
      if (kind === 'generate') {
        const result = await batchGenerateReports({ ...batchArgs, generatePartial })
        setActionMessage(
          t('classReports.generated', {
            count: result.generated_count,
            existing: result.skipped_existing_count,
            noResults: result.skipped_no_results_count,
            partial: result.skipped_partial_count,
          }),
        )
      } else if (kind === 'approve') {
        const result = await batchApproveReports(batchArgs)
        if (result.skipped_stale_count > 0 && window.confirm(t('classReports.confirmApproveStale', { count: result.skipped_stale_count }))) {
          const overrideResult = await batchApproveReports({ ...batchArgs, approveStale: true })
          setActionMessage(
            t('classReports.approvedWithStale', {
              count: overrideResult.approved_count,
              stale: result.skipped_stale_count,
            }),
          )
        } else {
          setActionMessage(
            t('classReports.approved', {
              count: result.approved_count,
              stale: result.skipped_stale_count,
            }),
          )
        }
      } else {
        const result = await batchSendReports(batchArgs)
        if (result.skipped_stale_count > 0 && window.confirm(t('classReports.confirmSendStale', { count: result.skipped_stale_count }))) {
          const overrideResult = await batchSendReports({ ...batchArgs, sendStale: true })
          setActionMessage(
            t('classReports.sent', {
              count: overrideResult.sent_count,
              failed: overrideResult.failed_count,
              noRecipient: overrideResult.no_recipient_count,
              stale: result.skipped_stale_count,
            }),
          )
        } else {
          setActionMessage(
            t('classReports.sent', {
              count: result.sent_count,
              failed: result.failed_count,
              noRecipient: result.no_recipient_count,
              stale: result.skipped_stale_count,
            }),
          )
        }
      }
      await loadStatus()
    } catch (err) {
      setActionError(err.message)
    } finally {
      setRunningAction(null)
    }
  }

  // Enqueue the merged class PDF and poll every 2s until it is ready (the
  // render outlives a single request on the free tier). 30 tries ≈ 1 minute.
  async function handleDownloadClassPdf() {
    setActionMessage(null)
    setActionError(null)
    setDownloadingPdf(true)
    try {
      const job = await createClassPdfJob(batchArgs)
      for (let attempt = 0; attempt < 30; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 2000))
        const result = await pollClassPdfJob(job.job_id)
        if (result.status === 'done') {
          const url = URL.createObjectURL(result.blob)
          const link = document.createElement('a')
          link.href = url
          link.download = `${status.class_name}_${term}_${schoolYear}_bulletins.pdf`.replace(/\s+/g, '-')
          document.body.appendChild(link)
          link.click()
          link.remove()
          URL.revokeObjectURL(url)
          setActionMessage(t('classReports.pdfReady'))
          return
        }
        if (result.status === 'failed') {
          setActionError(t('classReports.pdfFailed'))
          return
        }
      }
      setActionError(t('classReports.pdfTimeout'))
    } catch (err) {
      setActionError(err.message)
    } finally {
      setDownloadingPdf(false)
    }
  }

  async function handleRegenerate(row) {
    setActionMessage(null)
    setActionError(null)
    setRegeneratingId(row.report_id)
    try {
      await regenerateReport(row.report_id)
      setActionMessage(t('classReports.regenerated', { name: row.student_name }))
      await loadStatus()
    } catch (err) {
      setActionError(err.message)
    } finally {
      setRegeneratingId(null)
    }
  }

  const busy = Boolean(runningAction) || Boolean(regeneratingId) || downloadingPdf
  const printableCount = status ? status.approved_count + status.sent_count : 0

  return (
    <section className="admin-page">
      <Link to="/admin/reports" className="back-link">
        ← {t('nav.reports')}
      </Link>

      <div className="report-header">
        <div>
          <h2 className="page-title">{t('classReports.title')}</h2>
          <p className="muted">{t('classReports.subtitle')}</p>
        </div>
      </div>

      <div className="card workflow-card">
        <strong>{t('classReports.flowTitle')}</strong>
        <p className="muted">{t('classReports.flowSteps')}</p>
      </div>

      <div className="list-toolbar">
        <label className="toolbar-field">
          <span>{t('students.class')}</span>
          <ClassSelect classes={classes} value={classId} onChange={setClassId} disabled={busy} />
        </label>
        <label className="toolbar-field">
          <span>{t('common.term')}</span>
          <TermSelect value={term} onChange={setTerm} disabled={busy} required={false} />
        </label>
        {schoolYear && (
          <p className="muted">
            {t('common.schoolYear')}: {schoolYear}
          </p>
        )}
      </div>

      {error && <ErrorBanner message={error} />}
      {loading && <Spinner label={t('classReports.loading')} />}

      {status && !loading && (
        <>
          <p className="muted">
            {t('classReports.summary', {
              total: status.total_students,
              without: status.without_report_count,
              draft: status.draft_count,
              approved: status.approved_count,
              sent: status.sent_count,
              stale: status.needs_review_count,
            })}
          </p>

          <div className="grade-actions batch-actions">
            <button
              type="button"
                className="btn btn-primary"
                onClick={() => runBatch('generate')}
                disabled={busy || midTrimesterNoCompleteResults || (generatableCount === 0 && partialRows.length === 0)}
              >
                {runningAction === 'generate'
                  ? t('classReports.generating')
                  : t('classReports.generateAll', { count: generatableCount + partialRows.length })}
              </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => runBatch('approve')}
              disabled={busy || status.draft_count === 0}
            >
              {runningAction === 'approve'
                ? t('classReports.approving')
                : t('classReports.approveAll', { count: status.draft_count })}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => runBatch('send')}
              disabled={busy || status.approved_count === 0}
            >
              {runningAction === 'send'
                ? t('classReports.sending')
                : t('classReports.sendAll', { count: status.approved_count })}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={handleDownloadClassPdf}
              disabled={busy || printableCount === 0}
            >
              {downloadingPdf
                ? t('classReports.pdfGenerating')
                : t('classReports.downloadPdf', { count: printableCount })}
            </button>
          </div>

          {actionMessage && <p className="grade-summary">{actionMessage}</p>}
          {actionError && <ErrorBanner message={actionError} />}
          {midTrimesterNoCompleteResults && (
            <div className="state state-empty">
              {t('classReports.midTrimesterInProgress')}
            </div>
          )}

          {status.students.length === 0 ? (
            <Empty message={t('classReports.noStudents')} />
          ) : (
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>{t('reports.student')}</th>
                    <th>{t('students.studentNumber')}</th>
                    <th className="num">{t('classReports.results')}</th>
                    <th>{t('common.status')}</th>
                    <th className="num">{t('classReports.bilingualAverage')}</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {status.students.map((row) => (
                    <tr key={row.student_id}>
                      <td className="nowrap">
                        {row.report_id ? (
                          <Link className="link-action" to={`/admin/reports/${row.report_id}`}>
                            {row.student_name}
                          </Link>
                        ) : (
                          row.student_name
                        )}
                      </td>
                      <td className="mono nowrap">{row.student_number}</td>
                      <td className="num">
                        {row.expected_results_count > 0
                          ? t('classReports.resultProgress', {
                            results: row.expected_results_count - row.missing_results_count,
                            expected: row.expected_results_count,
                          })
                          : row.results_count}
                      </td>
                      <td className="nowrap">
                        {row.report_status ? (
                          <StatusBadge status={row.report_status} />
                        ) : row.results_count > 0 ? (
                          <span className="muted">{t('classReports.noReportYet')}</span>
                        ) : (
                          <span className="muted">{t('classReports.noResults')}</span>
                        )}
                        {row.needs_review && (
                          <span className="needs-review-text">
                            {t('classReports.needsReview')}
                          </span>
                        )}
                        {!midTrimesterNoCompleteResults && row.missing_results_count > 0 && (
                          <span className="needs-review-text">
                            {t('classReports.partialResults', {
                              results: row.expected_results_count - row.missing_results_count,
                              expected: row.expected_results_count,
                            })}
                          </span>
                        )}
                      </td>
                      <td className="num">
                        {midTrimesterNoCompleteResults
                          ? <span className="muted">{t('classReports.averageLater')}</span>
                          : row.bilingual_average != null
                          ? formatReportAverage(row.bilingual_average, '20')
                          : '—'}
                      </td>
                      <td className="nowrap">
                        {row.needs_review && (
                          <button
                            type="button"
                            className="link-action"
                            disabled={busy}
                            onClick={() => handleRegenerate(row)}
                          >
                            {regeneratingId === row.report_id
                              ? t('classReports.regenerating')
                              : t('classReports.regenerate')}
                          </button>
                        )}
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
