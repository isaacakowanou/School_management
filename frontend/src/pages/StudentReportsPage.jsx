import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
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
  const { t } = useTranslation()
  const [student, setStudent] = useState(null)
  const [reports, setReports] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    setReports(null)
    setStudent(null)

    async function load() {
      try {
        const reportList = await getStudentReports(studentId)
        if (cancelled) return
        setReports(reportList)
      } catch (err) {
        if (!cancelled) setError(err.message)
        return
      }
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
    <section className="parent-page">
      <Link to="/" className="back-link">
        {t('reports.myStudentsBack')}
      </Link>
      <div className="report-header">
        <div>
          <h2 className="page-title">
            {student ? `${student.first_name} ${student.last_name}` : t('nav.reports')}
          </h2>
          {student && (
            <p className="muted">
              {student.class_name || '—'} · #{student.student_number}
            </p>
          )}
        </div>
      </div>

      <nav className="parent-tabs" aria-label={t('parentGrades.studentSections')}>
        <Link className="parent-tab" to={`/students/${studentId}`}>
          {t('parentGrades.notes')}
        </Link>
        <span className="parent-tab parent-tab-active">{t('nav.reports')}</span>
      </nav>

      {error && <ErrorBanner message={error} />}
      {!error && reports === null && <Spinner label={t('reports.loading')} />}
      {!error && reports && reports.length === 0 && (
        <Empty message={t('reports.noPublished')} />
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
                  <div className="muted">{t('reports.average')} {formatReportAverage(report.bilingual_average ?? report.overall_average, report.scale)}</div>
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
