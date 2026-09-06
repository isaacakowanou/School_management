import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { downloadReportPdf, getReport } from '../api/reports.js'
import BulletinAcademicDetails from '../components/BulletinAcademicDetails.jsx'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'

export default function ReportDetailPage() {
  const { reportId } = useParams()
  const { t } = useTranslation()
  const [report, setReport] = useState(null)
  const [error, setError] = useState(null)
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    setReport(null)

    async function load() {
      try {
        const data = await getReport(reportId)
        if (cancelled) return
        setReport(data)
      } catch (err) {
        if (!cancelled) setError(err.message)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [reportId])

  async function handleDownload() {
    setDownloadError(null)
    setDownloading(true)
    try {
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
    } catch (err) {
      setDownloadError(err.message || t('reports.downloadFailed'))
    } finally {
      setDownloading(false)
    }
  }

  if (error) {
    return (
      <section className="parent-page">
        <Link to="/" className="back-link">
          {t('reports.myStudentsBack')}
        </Link>
        <ErrorBanner message={error} />
      </section>
    )
  }

  if (!report) {
    return (
      <section className="parent-page">
        <Spinner label={t('reports.loadingOne')} />
      </section>
    )
  }

  const studentName = report.student_name || t('reports.reportCard')

  return (
    <section className="parent-page">
      <Link to={`/students/${report.student_id}/reports`} className="back-link">
        ← {t('nav.reports')}
      </Link>

      <div className="report-header">
        <div>
          <h2 className="page-title">{studentName}</h2>
          <p className="muted">
            {report.term} · {report.school_year}
            {' '}· {report.student_class_name || '—'} · #{report.student_number || '—'}
          </p>
        </div>
        <button type="button" className="btn btn-primary" onClick={handleDownload} disabled={downloading}>
          {downloading ? t('reports.preparing') : t('reports.downloadPdf')}
        </button>
      </div>

      {downloadError && <ErrorBanner message={downloadError} />}

      <BulletinAcademicDetails report={report} showBehavior />

      {report.ai_summary && (
        <>
          <h3 className="section-title">{t('reports.parentSummarySection')}</h3>
          <div className="card summary-card">{report.ai_summary}</div>
        </>
      )}
    </section>
  )
}
