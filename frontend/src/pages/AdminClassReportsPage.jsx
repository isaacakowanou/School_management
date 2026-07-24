import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAcademicQueryParams } from '../academic/AcademicContext.jsx'
import {
  batchApproveReports,
  batchGenerateReports,
  batchSendReports,
  createClassPdfJob,
  createBulkReportGenerationJob,
  getClassReportStatus,
  getBulkReportGenerationJob,
  pollClassPdfJob,
  regenerateReport,
} from '../api/reports.js'
import { listClasses } from '../api/classes.js'
import { listTrimesterLocks, setTrimesterLock } from '../api/trimesterLocks.js'
import { TRIMESTER_TERMS } from '../constants/terms.js'
import { formatReportAverage } from '../utils/format.js'
import ClassSelect from '../components/ClassSelect.jsx'
import TermSelect from '../components/TermSelect.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'
import { bulkGenerationSummaryValues } from '../utils/reportGeneration.js'

export default function AdminClassReportsPage() {
  const { t } = useTranslation()
  const [classes, setClasses] = useState([])
  const [classId, setClassId] = useState('')
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [actionMessage, setActionMessage] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [runningAction, setRunningAction] = useState(null)
  const [regeneratingId, setRegeneratingId] = useState(null)
  const [downloadingPdf, setDownloadingPdf] = useState(false)
  const [trimesterLocks, setTrimesterLocks] = useState([])
  const [updatingLockTerm, setUpdatingLockTerm] = useState(null)
  const [lockError, setLockError] = useState(null)
  const [partialGenerationPrompt, setPartialGenerationPrompt] = useState(null)
  const {
    selectedSchoolYear,
    selectedTerm,
    setSelectedSchoolYear,
    setSelectedTerm,
    availableSchoolYears,
  } = useAcademicQueryParams()

  useEffect(() => {
    if (!selectedSchoolYear) return undefined
    let cancelled = false
    listClasses({ schoolYear: selectedSchoolYear })
      .then((data) => {
        if (cancelled) return
        setClasses(data)
        setClassId((current) => (data.some((item) => item.id === current) ? current : data[0]?.id || ''))
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [selectedSchoolYear])

  const selectedClass = useMemo(
    () => classes.find((item) => item.id === classId) || null,
    [classes, classId],
  )
  const schoolYear = selectedSchoolYear || selectedClass?.school_year || ''
  const batchArgs = useMemo(
    () => ({ classId, schoolYear, term: selectedTerm }),
    [classId, schoolYear, selectedTerm],
  )

  useEffect(() => {
    if (!classId && classes.length > 0) {
      setClassId(classes[0].id)
    }
  }, [classes, classId])

  useEffect(() => {
    let cancelled = false
    setLockError(null)
    if (!schoolYear) {
      setTrimesterLocks([])
      return () => { cancelled = true }
    }
    listTrimesterLocks(schoolYear)
      .then((data) => {
        if (!cancelled) setTrimesterLocks(data)
      })
      .catch((err) => {
        if (!cancelled) setLockError(err.message)
      })
    return () => { cancelled = true }
  }, [schoolYear])

  async function handleToggleLock(termToChange, currentlyLocked) {
    const confirmation = currentlyLocked
      ? t('classReports.confirmUnlockTrimester', { term: termToChange })
      : t('classReports.confirmLockTrimester', { term: termToChange })
    if (!window.confirm(confirmation)) return
    setUpdatingLockTerm(termToChange)
    setLockError(null)
    try {
      const updated = await setTrimesterLock({
        schoolYear,
        term: termToChange,
        isLocked: !currentlyLocked,
      })
      setTrimesterLocks((current) => current.map((lock) => (
        lock.term === updated.term ? updated : lock
      )))
    } catch (err) {
      setLockError(err.message)
    } finally {
      setUpdatingLockTerm(null)
    }
  }

  const loadStatus = useCallback(async () => {
    if (!classId || !selectedTerm || !schoolYear) {
      setStatus(null)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const data = await getClassReportStatus({ classId, schoolYear, term: selectedTerm })
      setStatus(data)
    } catch (err) {
      setError(err.message)
      setStatus(null)
    } finally {
      setLoading(false)
    }
  }, [classId, selectedTerm, schoolYear])

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

    if (kind === 'generate' && partialRows.length > 0) {
      setPartialGenerationPrompt({ scope: 'class', count: partialRows.length })
      return
    }

    await executeBatch(kind, false)
  }

  async function executeBatch(kind, generatePartial) {
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

  async function runBulkGenerate() {
    setActionMessage(null)
    setActionError(null)
    if (!window.confirm(t('classReports.confirmBulkGenerate', { schoolYear, term: selectedTerm }))) return
    setPartialGenerationPrompt({ scope: 'bulk' })
  }

  async function executeBulkGenerate(generatePartial) {
    setRunningAction('bulk-generate')
    try {
      const job = await createBulkReportGenerationJob({ schoolYear, term: selectedTerm, generatePartial })
      let latest = job
      for (let attempt = 0; attempt < 30 && latest.status === 'pending'; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 2000))
        latest = await getBulkReportGenerationJob(job.job_id)
      }
      if (latest.status === 'failed') {
        setActionError(latest.error || t('classReports.bulkFailed'))
        return
      }
      if (latest.status === 'pending') {
        setActionError(t('classReports.bulkTimeout'))
        return
      }
      setActionMessage(
        t('classReports.bulkGenerated', bulkGenerationSummaryValues(latest.result)),
      )
      await loadStatus()
    } catch (err) {
      setActionError(err.message)
    } finally {
      setRunningAction(null)
    }
  }

  function handlePartialGenerationChoice(generatePartial) {
    const prompt = partialGenerationPrompt
    setPartialGenerationPrompt(null)
    if (prompt?.scope === 'class') {
      executeBatch('generate', generatePartial)
    } else if (prompt?.scope === 'bulk') {
      executeBulkGenerate(generatePartial)
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
          link.download = `${status.class_name}_${selectedTerm}_${schoolYear}_bulletins.pdf`.replace(/\s+/g, '-')
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
          <span>{t('common.schoolYear')}</span>
          <select
            value={selectedSchoolYear}
            onChange={(event) => {
              setSelectedSchoolYear(event.target.value)
              setClassId('')
            }}
            disabled={busy}
          >
            {availableSchoolYears.map((year) => (
              <option key={year} value={year}>{year}</option>
            ))}
          </select>
        </label>
        <label className="toolbar-field">
          <span>{t('students.class')}</span>
          <ClassSelect
            classes={classes}
            value={classId}
            onChange={setClassId}
            disabled={busy}
            includeUnassigned={false}
          />
        </label>
        <label className="toolbar-field">
          <span>{t('common.term')}</span>
          <TermSelect value={selectedTerm} onChange={setSelectedTerm} disabled={busy} required />
        </label>
        {schoolYear && (
          <p className="muted">
            {t('common.schoolYear')}: {schoolYear}
          </p>
        )}
      </div>

      {schoolYear && (
        <section className="trimester-lock-panel" aria-labelledby="trimester-lock-title">
          <div>
            <h3 id="trimester-lock-title">{t('classReports.trimesterLockTitle')}</h3>
            <p className="muted">{t('classReports.trimesterLockScope')}</p>
          </div>
          <div className="trimester-lock-grid">
            {TRIMESTER_TERMS.map((lockTerm) => {
              const locked = trimesterLocks.find((item) => item.term === lockTerm)?.is_locked || false
              return (
                <div className="trimester-lock-row" key={lockTerm}>
                  <div>
                    <strong>{lockTerm}</strong>
                    <span className={`badge ${locked ? 'badge-review' : 'badge-approved'}`}>
                      {locked ? t('classReports.locked') : t('classReports.unlocked')}
                    </span>
                  </div>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    disabled={Boolean(updatingLockTerm)}
                    onClick={() => handleToggleLock(lockTerm, locked)}
                  >
                    {updatingLockTerm === lockTerm
                      ? t('common.saving')
                      : locked
                        ? t('classReports.unlock')
                        : t('classReports.lock')}
                  </button>
                </div>
              )
            })}
          </div>
          {lockError && <ErrorBanner message={lockError} />}
        </section>
      )}

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
              className="btn btn-ghost"
              onClick={runBulkGenerate}
              disabled={busy || !schoolYear || !selectedTerm}
            >
              {runningAction === 'bulk-generate'
                ? t('classReports.bulkGenerating')
                : t('classReports.bulkGenerateAllClasses')}
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

      {partialGenerationPrompt && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => setPartialGenerationPrompt(null)}
        >
          <div
            className="card modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="partial-generation-title"
            onClick={(event) => event.stopPropagation()}
          >
            <h3 id="partial-generation-title">{t('classReports.partialModalTitle')}</h3>
            <p>
              {partialGenerationPrompt.scope === 'class'
                ? t('classReports.partialModalClassBody', { count: partialGenerationPrompt.count })
                : t('classReports.partialModalBulkBody')}
            </p>
            <div className="form-actions">
              <button type="button" className="btn btn-ghost" onClick={() => setPartialGenerationPrompt(null)}>
                {t('common.cancel')}
              </button>
              <button type="button" className="btn btn-ghost" onClick={() => handlePartialGenerationChoice(false)}>
                {t('classReports.generateWithoutPartial')}
              </button>
              <button type="button" className="btn btn-primary" onClick={() => handlePartialGenerationChoice(true)}>
                {t('classReports.includePartial')}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
