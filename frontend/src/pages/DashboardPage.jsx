import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { FileText, GraduationCap } from 'lucide-react'
import { useAuth } from '../auth/AuthContext.jsx'
import { getParentStudents } from '../api/parents.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

export default function DashboardPage() {
  const { parentId, parent } = useAuth()
  const { t } = useTranslation()
  const [students, setStudents] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!parentId) return
    let cancelled = false
    setError(null)
    setStudents(null)
    getParentStudents(parentId)
      .then((data) => {
        if (!cancelled) setStudents(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [parentId])

  return (
    <section className="parent-page">
      <div className="report-header">
        <div>
          <h2 className="page-title">{t('dashboard.title')}</h2>
          {parent && <p className="muted">{t('dashboard.signedInAs', { name: parent.name })}</p>}
        </div>
      </div>

      {error && <ErrorBanner message={error} />}
      {!error && students === null && <Spinner label={t('dashboard.loading')} />}
      {!error && students && students.length === 0 && (
        <Empty message={t('dashboard.empty')} />
      )}
      {!error && students && students.length > 0 && (
        <ul className="card-list">
          {students.map((student) => (
            <li key={student.id}>
              <div className="card student-card parent-student-card">
                <div>
                  <Link className="student-name parent-student-name-link" to={`/students/${student.id}`}>
                    {student.first_name} {student.last_name}
                  </Link>
                  <div className="muted">
                    {student.class_name || '—'} · #{student.student_number}
                  </div>
                </div>
                <div className="parent-student-card-actions">
                  <Link className="parent-student-card-action" to={`/students/${student.id}`}>
                    <GraduationCap size={16} aria-hidden="true" /> {t('parentGrades.notes')}
                  </Link>
                  <Link className="parent-student-card-action" to={`/students/${student.id}/reports`}>
                    <FileText size={16} aria-hidden="true" /> {t('nav.reports')}
                  </Link>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
