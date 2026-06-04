import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { enrollStudentInCourse, getCourse, listCourseStudents } from '../api/courses.js'
import { listStudents } from '../api/students.js'
import { getTeacher } from '../api/teachers.js'
import { listGradeItems } from '../api/gradeItems.js'
import { listCourseResults } from '../api/courseResults.js'
import { formatPercent } from '../utils/format.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

export default function AdminCourseDetailPage() {
  const { courseId } = useParams()
  const [course, setCourse] = useState(null)
  const [teacher, setTeacher] = useState(null)
  const [students, setStudents] = useState([])
  const [allStudents, setAllStudents] = useState([])
  const [gradeItems, setGradeItems] = useState([])
  const [results, setResults] = useState([])
  const [error, setError] = useState(null)
  const [enrollStudentId, setEnrollStudentId] = useState('')
  const [enrolling, setEnrolling] = useState(false)
  const [enrollError, setEnrollError] = useState(null)
  const [enrollMessage, setEnrollMessage] = useState(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    setCourse(null)
    setTeacher(null)
    setStudents([])
    setAllStudents([])
    setGradeItems([])
    setResults([])
    setEnrollStudentId('')
    setEnrollError(null)
    setEnrollMessage(null)

    async function load() {
      let courseData
      try {
        courseData = await getCourse(courseId)
        if (cancelled) return
        setCourse(courseData)
      } catch (err) {
        if (!cancelled) setError(err.message)
        return
      }
      // Related data is best-effort; each section degrades independently.
      const [teacherRes, studentsRes, gradeItemsRes, resultsRes, allStudentsRes] = await Promise.allSettled([
        getTeacher(courseData.teacher_id),
        listCourseStudents(courseId),
        listGradeItems(courseId),
        listCourseResults(courseId),
        listStudents(),
      ])
      if (cancelled) return
      if (teacherRes.status === 'fulfilled') setTeacher(teacherRes.value)
      if (studentsRes.status === 'fulfilled') setStudents(studentsRes.value)
      if (gradeItemsRes.status === 'fulfilled') setGradeItems(gradeItemsRes.value)
      if (resultsRes.status === 'fulfilled') setResults(resultsRes.value)
      if (allStudentsRes.status === 'fulfilled') setAllStudents(allStudentsRes.value)
    }

    load()
    return () => {
      cancelled = true
    }
  }, [courseId])

  const studentNameById = useMemo(() => {
    const map = new Map()
    for (const student of students) {
      map.set(student.id, `${student.first_name} ${student.last_name}`)
    }
    return map
  }, [students])

  const enrolledStudentIds = useMemo(() => new Set(students.map((student) => student.id)), [students])
  const availableStudents = useMemo(
    () => allStudents.filter((student) => !enrolledStudentIds.has(student.id)),
    [allStudents, enrolledStudentIds],
  )

  useEffect(() => {
    if (availableStudents.length === 0) {
      if (enrollStudentId) setEnrollStudentId('')
      return
    }
    if (!availableStudents.some((student) => student.id === enrollStudentId)) {
      setEnrollStudentId(availableStudents[0].id)
    }
  }, [availableStudents, enrollStudentId])

  async function handleEnrollStudent(event) {
    event.preventDefault()
    setEnrollError(null)
    setEnrollMessage(null)

    if (!enrollStudentId) {
      setEnrollError('Choose a student to enroll.')
      return
    }

    setEnrolling(true)
    try {
      await enrollStudentInCourse(courseId, enrollStudentId)
      const refreshed = await listCourseStudents(courseId)
      setStudents(refreshed)
      setEnrollMessage('Student enrolled.')
    } catch (err) {
      setEnrollError(err.message)
    } finally {
      setEnrolling(false)
    }
  }

  if (error) {
    return (
      <section className="admin-page">
        <Link to="/admin/courses" className="back-link">
          ← Courses
        </Link>
        <ErrorBanner message={error} />
      </section>
    )
  }

  if (!course) {
    return (
      <section className="admin-page">
        <Spinner label="Loading course…" />
      </section>
    )
  }

  return (
    <section className="admin-page">
      <Link to="/admin/courses" className="back-link">
        ← Courses
      </Link>
      <h2 className="page-title">{course.name}</h2>
      <p className="muted">
        {course.code} · {course.grade_level} · {course.term} · {course.school_year}
      </p>
      <p className="muted">
        Teacher:{' '}
        {teacher ? (
          <Link className="back-link" to={`/admin/teachers/${teacher.id}`}>
            {teacher.name}
          </Link>
        ) : (
          <span className="audit-id" title={course.teacher_id}>
            {course.teacher_id}
          </span>
        )}
      </p>

      <h3 className="section-title">Enrolled students</h3>
      <form className="card admin-form" onSubmit={handleEnrollStudent}>
        <label className="field">
          <span>Student</span>
          <select
            className="grade-input"
            value={enrollStudentId}
            onChange={(event) => setEnrollStudentId(event.target.value)}
            disabled={enrolling || availableStudents.length === 0}
            required
            style={{ width: '100%', textAlign: 'left' }}
          >
            {availableStudents.length === 0 ? (
              <option value="">No available students</option>
            ) : (
              availableStudents.map((student) => (
                <option key={student.id} value={student.id}>
                  {student.first_name} {student.last_name} — #{student.student_number}
                </option>
              ))
            )}
          </select>
        </label>

        <div className="grade-actions">
          <button
            type="submit"
            className="btn btn-primary"
            disabled={enrolling || availableStudents.length === 0}
          >
            {enrolling ? 'Enrolling...' : 'Enroll student'}
          </button>
          {enrollMessage && <span className="grade-summary">{enrollMessage}</span>}
        </div>
        {enrollError && <ErrorBanner message={enrollError} />}
      </form>

      {students.length === 0 ? (
        <Empty message="No students enrolled in this course." />
      ) : (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Student #</th>
                <th>Grade level</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {students.map((student) => (
                <tr key={student.id}>
                  <td>
                    {student.first_name} {student.last_name}
                  </td>
                  <td className="nowrap">{student.student_number}</td>
                  <td className="nowrap">{student.grade_level}</td>
                  <td className="nowrap">
                    <Link className="back-link" to={`/admin/students/${student.id}`}>
                      Open →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3 className="section-title">Grade items</h3>
      {gradeItems.length === 0 ? (
        <Empty message="No grade items for this course." />
      ) : (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Category</th>
                <th className="num">Max score</th>
                <th className="num">Weight</th>
                <th>Term</th>
                <th>Due date</th>
              </tr>
            </thead>
            <tbody>
              {gradeItems.map((item) => (
                <tr key={item.id}>
                  <td>{item.title}</td>
                  <td className="nowrap">{item.category}</td>
                  <td className="num">{item.max_score}</td>
                  <td className="num">{item.weight}</td>
                  <td className="nowrap">{item.term}</td>
                  <td className="nowrap">{item.due_date || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3 className="section-title">Course results</h3>
      {results.length === 0 ? (
        <Empty message="No course results calculated for this course." />
      ) : (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Student</th>
                <th>Term</th>
                <th className="num">Average</th>
                <th className="num">Grade</th>
              </tr>
            </thead>
            <tbody>
              {results.map((result) => (
                <tr key={result.id}>
                  <td>
                    {studentNameById.get(result.student_id) || (
                      <span className="audit-id" title={result.student_id}>
                        {result.student_id}
                      </span>
                    )}
                  </td>
                  <td className="nowrap">{result.term}</td>
                  <td className="num">{formatPercent(result.average)}</td>
                  <td className="num">{result.letter_grade}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
