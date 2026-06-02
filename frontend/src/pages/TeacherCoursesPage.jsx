import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'
import { getMyCourses } from '../api/courses.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

export default function TeacherCoursesPage() {
  const { user } = useAuth()
  const [courses, setCourses] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    setCourses(null)
    getMyCourses()
      .then((data) => {
        if (!cancelled) setCourses(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <section className="teacher-page">
      <h2 className="page-title">My courses</h2>
      {user && <p className="muted">Signed in as {user.name}</p>}

      {error && <ErrorBanner message={error} />}
      {!error && courses === null && <Spinner label="Loading courses…" />}
      {!error && courses && courses.length === 0 && (
        <Empty message="No courses are assigned to your account yet." />
      )}
      {!error && courses && courses.length > 0 && (
        <ul className="card-list">
          {courses.map((course) => (
            <li key={course.id}>
              <Link className="card student-card" to={`/teacher/courses/${course.id}`}>
                <div className="student-name">{course.name}</div>
                <div className="muted">
                  {course.code} · {course.grade_level} · {course.term} {course.school_year}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
