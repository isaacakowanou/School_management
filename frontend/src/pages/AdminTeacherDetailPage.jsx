import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getTeacher, getTeacherCourses } from '../api/teachers.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

export default function AdminTeacherDetailPage() {
  const { teacherId } = useParams()
  const [teacher, setTeacher] = useState(null)
  const [courses, setCourses] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    setTeacher(null)
    setCourses([])

    async function load() {
      try {
        const data = await getTeacher(teacherId)
        if (cancelled) return
        setTeacher(data)
      } catch (err) {
        if (!cancelled) setError(err.message)
        return
      }
      // Assigned courses are best-effort.
      try {
        const list = await getTeacherCourses(teacherId)
        if (!cancelled) setCourses(list)
      } catch {
        /* non-fatal */
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [teacherId])

  if (error) {
    return (
      <section className="admin-page">
        <Link to="/admin/teachers" className="back-link">
          ← Teachers
        </Link>
        <ErrorBanner message={error} />
      </section>
    )
  }

  if (!teacher) {
    return (
      <section className="admin-page">
        <Spinner label="Loading teacher…" />
      </section>
    )
  }

  return (
    <section className="admin-page">
      <Link to="/admin/teachers" className="back-link">
        ← Teachers
      </Link>
      <h2 className="page-title">{teacher.name}</h2>
      <p className="muted">
        {teacher.email} · Employee #{teacher.employee_number}
      </p>

      <h3 className="section-title">Assigned courses</h3>
      {courses.length === 0 ? (
        <Empty message="No courses assigned to this teacher." />
      ) : (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Code</th>
                <th>Grade level</th>
                <th>Term</th>
                <th>School year</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {courses.map((course) => (
                <tr key={course.id}>
                  <td>{course.name}</td>
                  <td className="nowrap">{course.code}</td>
                  <td className="nowrap">{course.grade_level}</td>
                  <td className="nowrap">{course.term}</td>
                  <td className="nowrap">{course.school_year}</td>
                  <td className="nowrap">
                    <Link className="back-link" to={`/admin/courses/${course.id}`}>
                      Open →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
