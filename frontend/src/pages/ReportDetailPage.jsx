import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'
import { getParentStudents } from '../api/parents.js'
import { downloadReportPdf, getReport } from '../api/reports.js'
import { formatReportAverage } from '../utils/format.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'

export default function ReportDetailPage() {
  const { reportId } = useParams()
  const { parentId } = useAuth()
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
        // Resolve the student's name (best-effort; report payload has only student_id).
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
          ← My students
        </Link>
        <ErrorBanner message={error} />
      </section>
    )
  }

  if (!report) {
    return (
      <section>
        <Spinner label="Loading report…" />
      </section>
    )
  }

  const studentName = student ? `${student.first_name} ${student.last_name}` : 'Report card'

  return (
    <section>
      <Link to={`/students/${report.student_id}/reports`} className="back-link">
        ← Reports
      </Link>

      <div className="report-header">
        <div>
          <h2 className="page-title">{studentName}</h2>
          <p className="muted">
            {report.term} · {report.school_year}
            {student && (
              <>
                {' '}
                · {student.grade_level} · #{student.student_number}
              </>
            )}
          </p>
        </div>
        <button type="button" className="btn btn-primary" onClick={handleDownload} disabled={downloading}>
          {downloading ? 'Preparing…' : 'Download PDF'}
        </button>
      </div>

      {downloadError && <ErrorBanner message={downloadError} />}

      <div className="summary-row">
        <div className="stat">
          <div className="stat-label">Overall average</div>
          <div className="stat-value">{formatReportAverage(report.overall_average, report.scale)}</div>
        </div>
      </div>

      <h3 className="section-title">Courses</h3>
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
              <td className="num">{formatReportAverage(course.average, report.scale)}</td>
              <td className="num">{course.letter_grade}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {report.ai_summary && (
        <>
          <h3 className="section-title">Summary</h3>
          <div className="card summary-card">{report.ai_summary}</div>
        </>
      )}
    </section>
  )
}
