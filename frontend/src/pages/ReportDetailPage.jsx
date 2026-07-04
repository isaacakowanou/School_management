import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../auth/AuthContext.jsx'
import { getParentStudents } from '../api/parents.js'
import { downloadReportPdf, getReport } from '../api/reports.js'
import { formatReportAverage } from '../utils/format.js'
import ReportAverages from '../components/ReportAverages.jsx'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'

export default function ReportDetailPage() {
  const { reportId } = useParams()
  const { parentId } = useAuth()
  const { t } = useTranslation()
  const [report, setReport] = useState(null)
  const [student, setStudent] = useState(null)
  const [error, setError] = useState(null)
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    setReport(null)
    setStudent(null)

    async function load() {
      try {
        const data = await getReport(reportId)
        if (cancelled) return
        setReport(data)
        if (parentId) {
          try {
            const students = await getParentStudents(parentId)
            if (!cancelled) setStudent(students.find((s) => s.id === data.student_id) || null)
          } catch {
            /* non-fatal */
          }
        }
      } catch (err) {
        if (!cancelled) setError(err.message)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [reportId, parentId])

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
      setDownloadError(err.message || 'Could not download the PDF.')
    } finally {
      setDownloading(false)
    }
  }

  if (error) {
    return (
      <section>
        <Link to="/" className="back-link">
          {t('reports.myStudentsBack')}
        </Link>
        <ErrorBanner message={error} />
      </section>
    )
  }

  if (!report) {
    return (
      <section>
        <Spinner label={t('reports.loadingOne')} />
      </section>
    )
  }

  const studentName = student ? `${student.first_name} ${student.last_name}` : t('reports.reportCard')

  return (
    <section>
      <Link to={`/students/${report.student_id}/reports`} className="back-link">
        ← {t('nav.reports')}
      </Link>

      <div className="report-header">
        <div>
          <h2 className="page-title">{studentName}</h2>
          <p className="muted">
            {report.term} · {report.school_year}
            {student && (
              <>
                {' '}
                · {student.class_name || '—'} · #{student.student_number}
              </>
            )}
          </p>
        </div>
        <button type="button" className="btn btn-primary" onClick={handleDownload} disabled={downloading}>
          {downloading ? t('reports.preparing') : t('reports.downloadPdf')}
        </button>
      </div>

      {downloadError && <ErrorBanner message={downloadError} />}

      <div className="summary-row">
        <ReportAverages report={report} />
      </div>

      <h3 className="section-title">{t('reports.coursesSection')}</h3>
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

      {report.ai_summary && (
        <>
          <h3 className="section-title">{t('reports.parentSummarySection')}</h3>
          <div className="card summary-card">{report.ai_summary}</div>
        </>
      )}
    </section>
  )
}
