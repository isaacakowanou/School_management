import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { listArchivedCourses, listArchivedReports, listArchivedStudents } from '../api/archives.js'
import { formatReportAverage } from '../utils/format.js'
import Empty from '../components/Empty.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Spinner from '../components/Spinner.jsx'
import StatusBadge from '../components/StatusBadge.jsx'

const TABS = ['reports', 'courses', 'students']

export default function AdminArchivesPage() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = TABS.includes(searchParams.get('tab')) ? searchParams.get('tab') : 'reports'
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setRows(null)
    setError(null)
    const loader =
      activeTab === 'courses'
        ? listArchivedCourses
        : activeTab === 'students'
          ? listArchivedStudents
          : listArchivedReports
    loader()
      .then((data) => {
        if (!cancelled) setRows(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [activeTab])

  function setTab(tab) {
    const next = new URLSearchParams(searchParams)
    next.set('tab', tab)
    setSearchParams(next)
  }

  return (
    <section className="admin-page">
      <div className="report-header">
        <div>
          <h2 className="page-title">{t('archives.title')}</h2>
          <p className="muted">{t('archives.subtitle')}</p>
        </div>
      </div>

      <div className="parent-tabs">
        {TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            className={`parent-tab${activeTab === tab ? ' parent-tab-active' : ''}`}
            onClick={() => setTab(tab)}
          >
            {t(`archives.${tab}`)}
          </button>
        ))}
      </div>

      {error && <ErrorBanner message={error} />}
      {!error && rows === null && <Spinner label={t('common.loading')} />}
      {!error && rows && rows.length === 0 && <Empty message={t('archives.empty')} />}
      {!error && rows && rows.length > 0 && activeTab === 'reports' && (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>{t('reports.student')}</th>
                <th>{t('reports.term')}</th>
                <th>{t('reports.schoolYear')}</th>
                <th>{t('common.status')}</th>
                <th className="num">{t('reports.average')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((report) => (
                <tr key={report.id}>
                  <td>
                    <div className="student-cell-main">{report.student_name}</div>
                    <div className="student-cell-meta">#{report.student_number}</div>
                  </td>
                  <td>{report.term}</td>
                  <td>{report.school_year}</td>
                  <td><StatusBadge status={report.needs_review ? 'needs_review' : report.status} /></td>
                  <td className="num">{formatReportAverage(report.bilingual_average ?? report.overall_average, report.scale)}</td>
                  <td><Link className="link-action" to={`/admin/reports/${report.id}`}>{t('common.open')}</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!error && rows && rows.length > 0 && activeTab === 'courses' && (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>{t('common.name')}</th>
                <th>{t('courses.code')}</th>
                <th>{t('students.class')}</th>
                <th>{t('common.term')}</th>
                <th>{t('common.schoolYear')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((course) => (
                <tr key={course.id}>
                  <td>{course.name}</td>
                  <td>{course.code}</td>
                  <td>{course.class_name || '—'}</td>
                  <td>{course.term}</td>
                  <td>{course.school_year}</td>
                  <td><Link className="link-action" to={`/admin/courses/${course.id}`}>{t('common.open')}</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!error && rows && rows.length > 0 && activeTab === 'students' && (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>{t('common.name')}</th>
                <th>{t('students.studentNumber')}</th>
                <th>{t('students.class')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((student) => (
                <tr key={student.id}>
                  <td>{student.first_name} {student.last_name}</td>
                  <td>{student.student_number}</td>
                  <td>{student.class_name || student.historical_class_name || 'Diplômé'}</td>
                  <td><Link className="link-action" to={`/admin/students/${student.id}`}>{t('common.open')}</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
