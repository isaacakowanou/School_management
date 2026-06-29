import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'
import { getParentStudents } from '../api/parents.js'
import { getStudentReports } from '../api/reports.js'
import { formatReportAverage } from '../utils/format.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'
import StatusBadge from '../components/StatusBadge.jsx'

export default function StudentReportsPage() {
  const { studentId } = useParams()
  const { parentId } = useAuth()
  const [student, setStudent] = useState(null)
  const [reports, setReports] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    setReports(null)
    setStudent(null)

    async function load() {
      // Reports are the primary content (already filtered to approved/sent by the API).
      try {
        const reportList = await getStudentReports(studentId)
        if (cancelled) return
        setReports(reportList)
      } catch (err) {
        if (!cancelled) setError(err.message)
        return
      }
      // Student name/details are best-effort (the reports payload has no name).
      if (parentId) {
        try {
          const students = await getParentStudents(parentId)
          if (!cancelled) setStudent(students.find((s) => s.id === studentId) || null)
        } catch {
          /* non-fatal: header just falls back to a generic title */
        }
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [studentId, parentId])

  return (
    <section>
      <Link to="/" className="back-link">
        ← My students
      </Link>
      <h2 className="page-title">
        {student ? `${student.first_name} ${student.last_name}` : 'Reports'}
      </h2>
      {student && (
        <p className="muted">
          {student.grade_level} · #{student.student_number}
        </p>
      )}

      {error && <ErrorBanner message={error} />}
      {!error && reports === null && <Spinner label="Loading reports…" />}
      {!error && reports && reports.length === 0 && (
        <Empty message="No published reports are available yet." />
      )}
      {!error && reports && reports.length > 0 && (
        <ul className="card-list">
          {reports.map((report) => (
            <li key={report.id}>
              <Link className="card report-row" to={`/reports/${report.id}`}>
                <div>
                  <div className="report-term">
                    {report.term} · {report.school_year}
                  </div>
                  <div className="muted">Overall {formatReportAverage(report.overall_average, report.scale)}</div>
                </div>
                <StatusBadge status={report.status} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
