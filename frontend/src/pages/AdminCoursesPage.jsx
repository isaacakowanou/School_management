import { useEffect, useMemo, useState } from 'react'
import { listCourses } from '../api/courses.js'
import { listTeachers } from '../api/teachers.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

export default function AdminCoursesPage() {
  const [courses, setCourses] = useState(null)
  const [teachers, setTeachers] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    setCourses(null)
    setTeachers([])

    async function load() {
      // Courses are the primary content.
      try {
        const courseList = await listCourses()
        if (cancelled) return
        setCourses(courseList)
      } catch (err) {
        if (!cancelled) setError(err.message)
        return
      }
      // Teacher names are a best-effort join (CourseResponse only carries teacher_id);
      // if this fails we fall back to showing the id.
      try {
        const teacherList = await listTeachers()
        if (!cancelled) setTeachers(teacherList)
      } catch {
        /* non-fatal */
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [])

  const teacherNameById = useMemo(() => {
    const map = new Map()
    for (const teacher of teachers) map.set(teacher.id, teacher.name)
    return map
  }, [teachers])

  return (
    <section className="admin-page">
      <h2 className="page-title">Courses</h2>
      <p className="muted">All courses, read-only.</p>

      {error && <ErrorBanner message={error} />}
      {!error && courses === null && <Spinner label="Loading courses…" />}
      {!error && courses && courses.length === 0 && <Empty message="No courses found." />}
      {!error && courses && courses.length > 0 && (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Code</th>
                <th>Teacher</th>
                <th>Grade level</th>
                <th>Term</th>
                <th>School year</th>
              </tr>
            </thead>
            <tbody>
              {courses.map((course) => (
                <tr key={course.id}>
                  <td>{course.name}</td>
                  <td className="nowrap">{course.code}</td>
                  <td>
                    {teacherNameById.get(course.teacher_id) || (
                      <span className="audit-id" title={course.teacher_id}>
                        {course.teacher_id}
                      </span>
                    )}
                  </td>
                  <td className="nowrap">{course.grade_level}</td>
                  <td className="nowrap">{course.term}</td>
                  <td className="nowrap">{course.school_year}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
