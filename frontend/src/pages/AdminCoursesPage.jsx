import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { cloneYearCourses, listCourses } from '../api/courses.js'
import { listTeachers } from '../api/teachers.js'
import { schoolGroupLabel } from '../constants/schoolGroups.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

const TARGET_YEAR_SUGGESTIONS = ['2027-2028', '2028-2029', '2029-2030']

export default function AdminCoursesPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const [courses, setCourses] = useState(null)
  const [teachers, setTeachers] = useState([])
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(location.state?.message || null)

  const [showCloneDialog, setShowCloneDialog] = useState(false)
  const [cloneSourceYear, setCloneSourceYear] = useState('')
  const [cloneTargetYear, setCloneTargetYear] = useState('')
  const [cloneError, setCloneError] = useState(null)
  const [cloning, setCloning] = useState(false)

  useEffect(() => {
    if (location.state?.message) {
      navigate(location.pathname, { replace: true, state: {} })
    }
  }, [location.pathname, location.state, navigate])

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

  const courseCountByYear = useMemo(() => {
    const map = new Map()
    for (const course of courses || []) {
      map.set(course.school_year, (map.get(course.school_year) || 0) + 1)
    }
    return map
  }, [courses])

  const schoolYears = useMemo(
    () => Array.from(courseCountByYear.keys()).sort().reverse(),
    [courseCountByYear],
  )

  const cloneSourceCount = courseCountByYear.get(cloneSourceYear) || 0
  const cloneTargetCount = courseCountByYear.get(cloneTargetYear.trim()) || 0

  function openCloneDialog() {
    setCloneSourceYear(schoolYears[0] || '')
    setCloneTargetYear('')
    setCloneError(null)
    setShowCloneDialog(true)
  }

  async function handleClone(event) {
    event.preventDefault()
    setCloneError(null)
    if (!cloneSourceYear || !cloneTargetYear.trim()) {
      setCloneError('Choose a source year and enter a target year.')
      return
    }
    setCloning(true)
    try {
      const result = await cloneYearCourses({
        sourceYear: cloneSourceYear,
        targetYear: cloneTargetYear,
      })
      const refreshed = await listCourses()
      setCourses(refreshed)
      setShowCloneDialog(false)
      let text = `Cloned ${result.created_count} course(s) into ${cloneTargetYear.trim()}.`
      if (result.unmatched_class_names.length) {
        text +=
          ` No matching class in ${cloneTargetYear.trim()} for: ` +
          `${result.unmatched_class_names.join(', ')} — those courses were left unassigned. ` +
          'Create the classes, then reassign from each course page.'
      }
      setNotice(text)
    } catch (err) {
      if (err.status === 409 && err.detail && typeof err.detail === 'object') {
        if (err.detail.course_count != null) {
          setCloneError(
            `${cloneTargetYear.trim()} already has ${err.detail.course_count} course(s). ` +
              'Cloning into a non-empty year is not allowed.',
          )
        } else if (err.detail.codes) {
          setCloneError(`These course codes already exist: ${err.detail.codes.join(', ')}.`)
        } else {
          setCloneError(err.message)
        }
      } else {
        setCloneError(err.message)
      }
    } finally {
      setCloning(false)
    }
  }

  return (
    <section className="admin-page">
      <div className="report-header">
        <div>
          <h2 className="page-title">Courses</h2>
          <p className="muted">All courses.</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={openCloneDialog}
            disabled={!courses || courses.length === 0}
          >
            Clone year
          </button>
          <Link to="/admin/courses/new" className="btn btn-primary">
            Add course
          </Link>
        </div>
      </div>

      {notice && <p className="grade-summary">{notice}</p>}
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
                <th>Group</th>
                <th></th>
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
                  <td className="nowrap">{schoolGroupLabel(course.language_group) || '—'}</td>
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

      {showCloneDialog && (
        <div
          onClick={() => setShowCloneDialog(false)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 16,
            zIndex: 1000,
          }}
        >
          <div
            className="card"
            onClick={(e) => e.stopPropagation()}
            style={{ maxWidth: 480, width: '100%', maxHeight: '90vh', overflowY: 'auto' }}
          >
            <h3 className="section-title">Clone courses to a new school year</h3>
            <p className="muted">
              Copies every course (subject, class, language group, teacher) from the source year.
              Grade items and enrollments are not copied. Classes are matched by name in the
              target year.
            </p>
            <form className="admin-form" onSubmit={handleClone}>
              <label className="field">
                <span>From school year</span>
                <select
                  className="grade-input"
                  value={cloneSourceYear}
                  onChange={(e) => setCloneSourceYear(e.target.value)}
                  disabled={cloning}
                  style={{ width: '100%', textAlign: 'left' }}
                >
                  {schoolYears.map((year) => (
                    <option key={year} value={year}>
                      {year} ({courseCountByYear.get(year)} course{courseCountByYear.get(year) === 1 ? '' : 's'})
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>To school year</span>
                <input
                  value={cloneTargetYear}
                  onChange={(e) => setCloneTargetYear(e.target.value)}
                  disabled={cloning}
                  list="clone-target-year-options"
                  placeholder="e.g. 2027-2028"
                  required
                />
              </label>
              <datalist id="clone-target-year-options">
                {TARGET_YEAR_SUGGESTIONS.filter((year) => year !== cloneSourceYear).map((year) => (
                  <option key={year} value={year} />
                ))}
              </datalist>

              {cloneTargetYear.trim() && cloneTargetCount > 0 && (
                <ErrorBanner
                  message={`${cloneTargetYear.trim()} already has ${cloneTargetCount} course(s). Cloning into a non-empty year is not allowed.`}
                />
              )}

              <div className="grade-actions">
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={
                    cloning ||
                    !cloneSourceYear ||
                    !cloneTargetYear.trim() ||
                    cloneTargetYear.trim() === cloneSourceYear ||
                    cloneTargetCount > 0
                  }
                >
                  {cloning
                    ? 'Cloning…'
                    : `Clone ${cloneSourceCount} course${cloneSourceCount === 1 ? '' : 's'}`}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => setShowCloneDialog(false)}
                  disabled={cloning}
                >
                  Cancel
                </button>
              </div>
              {cloneError && <ErrorBanner message={cloneError} />}
            </form>
          </div>
        </div>
      )}
    </section>
  )
}
