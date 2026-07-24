import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAcademicQueryParams } from '../academic/AcademicContext.jsx'
import { getParentStudentGrades, getParentStudents } from '../api/parents.js'
import { useAuth } from '../auth/AuthContext.jsx'
import { TRIMESTER_TERMS } from '../constants/terms.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

function formatDate(value, language) {
  if (!value) return '—'
  return new Intl.DateTimeFormat(language === 'fr' ? 'fr-FR' : 'en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(new Date(value))
}

function itemTypeLabel(grade, t) {
  if (grade.item_type) {
    return t(`courses.${grade.item_type.toLowerCase()}Label`, { defaultValue: grade.item_type })
  }
  return grade.category || t('courses.gradeItem')
}

function groupByCourse(grades) {
  const groups = []
  const byCourse = new Map()
  for (const grade of grades) {
    if (!byCourse.has(grade.course_id)) {
      const group = { courseId: grade.course_id, courseName: grade.course_name, items: [] }
      byCourse.set(grade.course_id, group)
      groups.push(group)
    }
    byCourse.get(grade.course_id).items.push(grade)
  }
  return groups
}

export default function ParentStudentPage() {
  const { studentId } = useParams()
  const { parentId } = useAuth()
  const { t, i18n } = useTranslation()
  const [student, setStudent] = useState(null)
  const [grades, setGrades] = useState(null)
  const [studentError, setStudentError] = useState(null)
  const [gradeError, setGradeError] = useState(null)
  const {
    selectedSchoolYear,
    selectedTerm,
    setSelectedSchoolYear,
    setSelectedTerm,
    availableSchoolYears,
    terms,
  } = useAcademicQueryParams()

  useEffect(() => {
    if (!parentId) return undefined
    let cancelled = false
    setStudent(null)
    setStudentError(null)
    getParentStudents(parentId)
      .then((students) => {
        if (!cancelled) setStudent(students.find((s) => s.id === studentId) || null)
      })
      .catch((err) => {
        if (!cancelled) setStudentError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [parentId, studentId])

  useEffect(() => {
    if (!selectedSchoolYear || !selectedTerm) return undefined
    let cancelled = false
    setGrades(null)
    setGradeError(null)
    getParentStudentGrades(studentId, { schoolYear: selectedSchoolYear, term: selectedTerm })
      .then((data) => {
        if (!cancelled) setGrades(data)
      })
      .catch((err) => {
        if (!cancelled) setGradeError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [studentId, selectedSchoolYear, selectedTerm])

  const recentGrades = useMemo(() => (grades || []).slice(0, 5), [grades])
  const courseGroups = useMemo(() => groupByCourse(grades || []), [grades])
  const studentName = student ? `${student.first_name} ${student.last_name}` : t('students.title')

  return (
    <section className="parent-page">
      <Link to="/" className="back-link">
        {t('reports.myStudentsBack')}
      </Link>

      <div className="report-header">
        <div>
          <h2 className="page-title">{studentName}</h2>
          {student && (
            <p className="muted">
              {student.class_name || '—'} · #{student.student_number}
            </p>
          )}
        </div>
      </div>

      <nav className="parent-tabs" aria-label={t('parentGrades.studentSections')}>
        <span className="parent-tab parent-tab-active">{t('parentGrades.notes')}</span>
        <Link className="parent-tab" to={`/students/${studentId}/reports`}>
          {t('nav.reports')}
        </Link>
      </nav>

      {studentError && <ErrorBanner message={studentError} />}

      <div className="section-heading">
        <div>
          <h3>{t('parentGrades.title')}</h3>
          <p className="muted">{t('parentGrades.subtitle')}</p>
        </div>
        <label className="field compact-field">
          <span>{t('common.schoolYear')}</span>
          <select value={selectedSchoolYear} onChange={(event) => setSelectedSchoolYear(event.target.value)}>
            {availableSchoolYears.map((year) => (
              <option key={year} value={year}>{year}</option>
            ))}
          </select>
        </label>
        <label className="field compact-field">
          <span>{t('common.term')}</span>
          <select value={selectedTerm} onChange={(event) => setSelectedTerm(event.target.value)}>
            {(terms.length ? terms : TRIMESTER_TERMS).map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
          <span className="muted">{t('parentGrades.averageAvailableWithReport')}</span>
        </label>
      </div>

      {gradeError && <ErrorBanner message={gradeError} />}
      {!gradeError && grades === null && <Spinner label={t('parentGrades.loading')} />}
      {!gradeError && grades && grades.length === 0 && (
        <Empty message={t('parentGrades.emptyTerm')} />
      )}
      {!gradeError && grades && grades.length > 0 && (
        <>
          <h3 className="section-title">{t('parentGrades.recent')}</h3>
          <div className="recent-grade-strip">
            {recentGrades.map((grade) => (
              <div className="recent-grade-card" key={`${grade.grade_item_id}-${grade.updated_at}`}>
                <div className="muted">{grade.course_name}</div>
                <strong>{grade.item_title}</strong>
                <div className="stat-value stat-value-compact">{grade.score} / {grade.max_score}</div>
                <div className="muted">{formatDate(grade.updated_at || grade.created_at, i18n.language)}</div>
              </div>
            ))}
          </div>

          <h3 className="section-title">{t('parentGrades.byCourse')}</h3>
          <div className="grade-course-list">
            {courseGroups.map((group) => (
              <section className="card" key={group.courseId}>
                <h4 className="card-title">{group.courseName}</h4>
                <div className="table-scroll">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>{t('parentGrades.item')}</th>
                        <th>{t('parentGrades.type')}</th>
                        <th className="num">{t('parentGrades.score')}</th>
                        <th>{t('parentGrades.date')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {group.items.map((grade) => (
                        <tr key={grade.grade_item_id}>
                          <td>{grade.item_title}</td>
                          <td>{itemTypeLabel(grade, t)}</td>
                          <td className="num">{grade.score} / {grade.max_score}</td>
                          <td>{formatDate(grade.updated_at || grade.created_at, i18n.language)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            ))}
          </div>
        </>
      )}
    </section>
  )
}
