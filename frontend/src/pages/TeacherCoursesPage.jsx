import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { BookOpen, CheckCircle2, GraduationCap, Library } from 'lucide-react'
import { useAcademicQueryParams } from '../academic/AcademicContext.jsx'
import { getMyCourses } from '../api/courses.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

export default function TeacherCoursesPage() {
  const { t } = useTranslation()
  const [courses, setCourses] = useState(null)
  const [error, setError] = useState(null)
  const {
    selectedSchoolYear,
    selectedTerm,
    setSelectedSchoolYear,
    setSelectedTerm,
    availableSchoolYears,
    terms,
  } = useAcademicQueryParams()

  useEffect(() => {
    if (!selectedSchoolYear || !selectedTerm) return undefined
    let cancelled = false
    setError(null)
    setCourses(null)
    getMyCourses({ schoolYear: selectedSchoolYear, term: selectedTerm })
      .then((data) => {
        if (!cancelled) setCourses(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [selectedSchoolYear, selectedTerm])

  return (
    <section className="teacher-page">
      <div className="report-header">
        <div>
          <h2 className="page-title">{t('courses.myCourses')}</h2>
          <p className="muted">{t('courses.myCoursesSubtitle')}</p>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}
      <div className="list-toolbar">
        <label className="toolbar-field">
          <span>{t('common.schoolYear')}</span>
          <select value={selectedSchoolYear} onChange={(event) => setSelectedSchoolYear(event.target.value)}>
            {availableSchoolYears.map((year) => (
              <option key={year} value={year}>{year}</option>
            ))}
          </select>
        </label>
        <label className="toolbar-field">
          <span>{t('common.term')}</span>
          <select value={selectedTerm} onChange={(event) => setSelectedTerm(event.target.value)}>
            {terms.map((term) => (
              <option key={term} value={term}>{term}</option>
            ))}
          </select>
        </label>
      </div>
      {!error && courses === null && <Spinner label={t('courses.loading')} />}
      {!error && courses && courses.length === 0 && (
        <Empty message={t('courses.noAssigned')} />
      )}
      {!error && courses && courses.length > 0 && (
        <ul className="teacher-course-grid">
          {courses.map((course) => (
            <li key={course.id}>
              <Link className="teacher-course-card" to={`/teacher/courses/${course.id}`}>
                <div className="teacher-course-card-main">
                  <span className="admin-stat-icon teacher-course-icon">
                    <BookOpen size={18} aria-hidden="true" />
                  </span>
                  <div>
                    <div className="student-name">{course.name}</div>
                    <div className="muted">
                      {course.code} · {course.class_name || t('courses.withoutClass')} · {course.term} {course.school_year}
                    </div>
                  </div>
                </div>
                <div className="teacher-course-stats">
                  <span>
                    <GraduationCap size={16} aria-hidden="true" />
                    {t('courses.studentCount', { count: course.student_count || 0 })}
                  </span>
                  <span>
                    <Library size={16} aria-hidden="true" />
                    {t('courses.gradeItemCount', { count: course.grade_item_count || 0 })}
                  </span>
                  <span>
                    <CheckCircle2 size={16} aria-hidden="true" />
                    {t('courses.entryProgress', {
                      filled: course.filled_score_count || 0,
                      total: course.possible_score_count || 0,
                    })}
                  </span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
