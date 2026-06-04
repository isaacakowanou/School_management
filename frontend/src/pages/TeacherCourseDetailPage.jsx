import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getCourse, listCourseStudents } from '../api/courses.js'
import { listGradeItems } from '../api/gradeItems.js'
import { listCourseGrades } from '../api/grades.js'
import {
  calculateCourseResults,
  calculateSelectedCourseResults,
  listCourseResults,
} from '../api/courseResults.js'
import { formatPercent } from '../utils/format.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'
import GradeEntryTable from '../components/GradeEntryTable.jsx'

export default function TeacherCourseDetailPage() {
  const { courseId } = useParams()

  const [course, setCourse] = useState(null)
  const [students, setStudents] = useState(null)
  const [gradeItems, setGradeItems] = useState(null)
  const [grades, setGrades] = useState(null)
  const [results, setResults] = useState(null)
  const [error, setError] = useState(null)

  const [calculating, setCalculating] = useState(false)
  const [calcSummary, setCalcSummary] = useState(null)
  const [calcError, setCalcError] = useState(null)
  const [pendingRecalcStudentIds, setPendingRecalcStudentIds] = useState([])

  useEffect(() => {
    let cancelled = false
    setError(null)
    setCourse(null)
    setStudents(null)
    setGradeItems(null)
    setGrades(null)
    setResults(null)
    setCalcSummary(null)
    setCalcError(null)
    setPendingRecalcStudentIds([])

    async function load() {
      try {
        const [c, s, gi, g, r] = await Promise.all([
          getCourse(courseId),
          listCourseStudents(courseId),
          listGradeItems(courseId),
          listCourseGrades(courseId),
          listCourseResults(courseId),
        ])
        if (cancelled) return
        setCourse(c)
        setStudents(s)
        setGradeItems(gi)
        setGrades(g)
        setResults(r)
      } catch (err) {
        if (!cancelled) setError(err.message)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [courseId])

  // Refresh grades after a save so the matrix reflects newly created grade ids.
  const handleGradesSaved = useCallback(async (changedStudentIds = []) => {
    if (changedStudentIds.length > 0) {
      setPendingRecalcStudentIds((current) =>
        Array.from(new Set([...current, ...changedStudentIds])),
      )
      setCalcSummary(null)
      setCalcError(null)
    }

    try {
      const g = await listCourseGrades(courseId)
      setGrades(g)
    } catch {
      /* non-fatal: keep current matrix state */
    }
  }, [courseId])

  async function handleRecalculate() {
    setCalculating(true)
    setCalcError(null)
    setCalcSummary(null)
    try {
      const shouldBootstrapAllResults = pendingRecalcStudentIds.length === 0 && results.length === 0
      if (pendingRecalcStudentIds.length === 0 && !shouldBootstrapAllResults) {
        setCalcSummary({
          calculated_count: 0,
          skipped_students: [],
          no_changes: true,
        })
        return
      }

      const studentIdsToRecalculate = [...pendingRecalcStudentIds]
      const res = shouldBootstrapAllResults
        ? await calculateCourseResults(courseId)
        : await calculateSelectedCourseResults(courseId, studentIdsToRecalculate)
      const calculatedStudentIds = new Set((res.results || []).map((result) => result.student_id))
      if (!shouldBootstrapAllResults) {
        setPendingRecalcStudentIds((current) =>
          current.filter((studentId) => !calculatedStudentIds.has(studentId)),
        )
      }
      setCalcSummary({
        calculated_count: res.calculated_count,
        skipped_students: res.skipped_students || [],
        no_changes: false,
      })
      const refreshed = await listCourseResults(courseId)
      setResults(refreshed)
    } catch (err) {
      setCalcError(err.message)
    } finally {
      setCalculating(false)
    }
  }

  const studentNameById = useMemo(() => {
    const map = {}
    for (const s of students || []) {
      map[s.id] = `${s.last_name}, ${s.first_name}`
    }
    return map
  }, [students])

  const loaded = course && students && gradeItems && grades && results

  return (
    <section className="teacher-page">
      <Link to="/teacher" className="back-link">
        ← My courses
      </Link>

      {error && <ErrorBanner message={error} />}
      {!error && !loaded && <Spinner label="Loading course…" />}

      {!error && loaded && (
        <>
          <h2 className="page-title">{course.name}</h2>
          <p className="muted">
            {course.code} · {course.grade_level} · {course.term} {course.school_year}
          </p>

          <h3 className="section-title">Enrolled students</h3>
          {students.length === 0 ? (
            <Empty message="No students are enrolled in this course yet." />
          ) : (
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>Student</th>
                    <th>Grade level</th>
                    <th>Student #</th>
                  </tr>
                </thead>
                <tbody>
                  {students.map((student) => (
                    <tr key={student.id}>
                      <td className="nowrap">
                        {student.last_name}, {student.first_name}
                      </td>
                      <td>{student.grade_level}</td>
                      <td className="mono">{student.student_number}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <h3 className="section-title">Grade items</h3>
          {gradeItems.length === 0 ? (
            <Empty message="This course has no grade items yet." />
          ) : (
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Category</th>
                    <th className="num">Weight</th>
                    <th className="num">Max score</th>
                    <th>Term</th>
                  </tr>
                </thead>
                <tbody>
                  {gradeItems.map((item) => (
                    <tr key={item.id}>
                      <td>{item.title}</td>
                      <td>{item.category}</td>
                      <td className="num">{item.weight}</td>
                      <td className="num">{item.max_score}</td>
                      <td>{item.term}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <h3 className="section-title">Grade entry</h3>
          <GradeEntryTable
            students={students}
            gradeItems={gradeItems}
            grades={grades}
            onSaved={handleGradesSaved}
          />

          <h3 className="section-title">Course results</h3>
          <div className="grade-actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleRecalculate}
              disabled={calculating}
            >
              {calculating ? 'Recalculating…' : 'Recalculate results'}
            </button>
            {calcSummary && (
              <span className="grade-summary">
                {calcSummary.no_changes ? 'No grade changes to recalculate.' : 'Results recalculated.'}
              </span>
            )}
          </div>

          {calcError && <ErrorBanner message={calcError} />}

          {calcSummary && calcSummary.skipped_students.length > 0 && (
            <div className="state state-empty skipped-note">
              <strong>Skipped (missing grades):</strong>
              <ul className="skipped-list">
                {calcSummary.skipped_students.map((skipped) => (
                  <li key={skipped.student_id}>
                    {skipped.student_name} — missing: {skipped.missing_grade_items.join(', ')}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {results.length === 0 ? (
            <Empty message="No results yet. Use “Recalculate results” to generate them." />
          ) : (
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>Student</th>
                    <th>Term</th>
                    <th className="num">Average</th>
                    <th>Letter</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((result) => (
                    <tr key={result.id}>
                      <td className="nowrap">
                        {studentNameById[result.student_id] || result.student_id}
                      </td>
                      <td>{result.term}</td>
                      <td className="num">{formatPercent(result.average)}</td>
                      <td>{result.letter_grade}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  )
}
