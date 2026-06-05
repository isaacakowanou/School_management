import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  enrollStudentInCourse,
  getCourse,
  listCourseStudents,
  unenrollStudentFromCourse,
  updateCourse,
} from '../api/courses.js'
import { listStudents } from '../api/students.js'
import { getTeacher, listTeachers } from '../api/teachers.js'
import { createGradeItem, listGradeItems, updateGradeItem } from '../api/gradeItems.js'
import { listCourseResults } from '../api/courseResults.js'
import { formatPercent } from '../utils/format.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

const EMPTY_GRADE_ITEM_FORM = {
  title: '',
  category: '',
  maxScore: '100',
  weight: '',
  term: '',
}

const EMPTY_COURSE_EDIT_FORM = {
  name: '',
  code: '',
  teacherId: '',
  gradeLevel: '',
  term: '',
  schoolYear: '',
}

const GRADE_ITEM_SUGGESTIONS = [
  'Homework',
  'Quiz',
  'Exam',
  'Midterm',
  'Final',
  'Project',
  'Participation',
]

const GRADE_LEVEL_SUGGESTIONS = [
  'Grade 6',
  'Grade 7',
  'Grade 8',
  'Grade 9',
  'Grade 10',
  'Grade 11',
  'Grade 12',
]
const TERM_SUGGESTIONS = ['Fall', 'Spring', 'Summer', 'Trimester 1', 'Trimester 2', 'Trimester 3']
const SCHOOL_YEAR_SUGGESTIONS = ['2026-2027', '2027-2028', '2028-2029']
const WEIGHT_TOLERANCE = 0.005

function formatWeight(value) {
  return value.toFixed(2)
}

function courseToForm(course) {
  return {
    name: course?.name || '',
    code: course?.code || '',
    teacherId: course?.teacher_id || '',
    gradeLevel: course?.grade_level || '',
    term: course?.term || '',
    schoolYear: course?.school_year || '',
  }
}

function gradeItemToForm(gradeItem) {
  return {
    title: gradeItem?.title || '',
    category: gradeItem?.category || '',
    maxScore: gradeItem?.max_score != null ? String(gradeItem.max_score) : '',
    weight: gradeItem?.weight != null ? String(gradeItem.weight) : '',
    term: gradeItem?.term || '',
    dueDate: gradeItem?.due_date || '',
  }
}

export default function AdminCourseDetailPage() {
  const { courseId } = useParams()
  const [course, setCourse] = useState(null)
  const [teacher, setTeacher] = useState(null)
  const [allTeachers, setAllTeachers] = useState([])
  const [students, setStudents] = useState([])
  const [allStudents, setAllStudents] = useState([])
  const [gradeItems, setGradeItems] = useState([])
  const [results, setResults] = useState([])
  const [error, setError] = useState(null)
  const [enrollStudentId, setEnrollStudentId] = useState('')
  const [enrolling, setEnrolling] = useState(false)
  const [enrollError, setEnrollError] = useState(null)
  const [enrollMessage, setEnrollMessage] = useState(null)
  const [showEnrollForm, setShowEnrollForm] = useState(false)
  const [unenrollingStudentId, setUnenrollingStudentId] = useState(null)
  const [gradeItemForm, setGradeItemForm] = useState(EMPTY_GRADE_ITEM_FORM)
  const [addingGradeItem, setAddingGradeItem] = useState(false)
  const [gradeItemError, setGradeItemError] = useState(null)
  const [gradeItemMessage, setGradeItemMessage] = useState(null)
  const [showGradeItemForm, setShowGradeItemForm] = useState(false)
  const [showEditForm, setShowEditForm] = useState(false)
  const [editForm, setEditForm] = useState(EMPTY_COURSE_EDIT_FORM)
  const [savingEdit, setSavingEdit] = useState(false)
  const [editError, setEditError] = useState(null)
  const [editMessage, setEditMessage] = useState(null)
  const [editingGradeItemId, setEditingGradeItemId] = useState(null)
  const [editGradeItemForm, setEditGradeItemForm] = useState(gradeItemToForm(null))
  const [savingGradeItemEdit, setSavingGradeItemEdit] = useState(false)
  const [gradeItemEditError, setGradeItemEditError] = useState(null)

  const refreshCourseResults = useCallback(async () => {
    try {
      const refreshed = await listCourseResults(courseId)
      setResults(refreshed)
    } catch {
      /* non-fatal: keep the current course detail view visible */
    }
  }, [courseId])

  useEffect(() => {
    let cancelled = false
    setError(null)
    setCourse(null)
    setTeacher(null)
    setAllTeachers([])
    setStudents([])
    setAllStudents([])
    setGradeItems([])
    setResults([])
    setEnrollStudentId('')
    setEnrollError(null)
    setEnrollMessage(null)
    setShowEnrollForm(false)
    setUnenrollingStudentId(null)
    setGradeItemForm(EMPTY_GRADE_ITEM_FORM)
    setGradeItemError(null)
    setGradeItemMessage(null)
    setShowGradeItemForm(false)
    setShowEditForm(false)
    setEditForm(EMPTY_COURSE_EDIT_FORM)
    setSavingEdit(false)
    setEditError(null)
    setEditMessage(null)
    setEditingGradeItemId(null)
    setEditGradeItemForm(gradeItemToForm(null))
    setSavingGradeItemEdit(false)
    setGradeItemEditError(null)

    async function load() {
      let courseData
      try {
        courseData = await getCourse(courseId)
        if (cancelled) return
        setCourse(courseData)
        setEditForm(courseToForm(courseData))
        setGradeItemForm((current) => ({
          ...current,
          term: current.term || courseData.term || '',
        }))
      } catch (err) {
        if (!cancelled) setError(err.message)
        return
      }
      // Related data is best-effort; each section degrades independently.
      const [teacherRes, studentsRes, gradeItemsRes, resultsRes, allStudentsRes, allTeachersRes] = await Promise.allSettled([
        getTeacher(courseData.teacher_id),
        listCourseStudents(courseId),
        listGradeItems(courseId),
        listCourseResults(courseId),
        listStudents(),
        listTeachers(),
      ])
      if (cancelled) return
      if (teacherRes.status === 'fulfilled') setTeacher(teacherRes.value)
      if (studentsRes.status === 'fulfilled') setStudents(studentsRes.value)
      if (gradeItemsRes.status === 'fulfilled') setGradeItems(gradeItemsRes.value)
      if (resultsRes.status === 'fulfilled') setResults(resultsRes.value)
      if (allStudentsRes.status === 'fulfilled') setAllStudents(allStudentsRes.value)
      if (allTeachersRes.status === 'fulfilled') setAllTeachers(allTeachersRes.value)
    }

    load()
    return () => {
      cancelled = true
    }
  }, [courseId])

  useEffect(() => {
    function refreshWhenVisible() {
      if (document.visibilityState === 'visible') {
        refreshCourseResults()
      }
    }

    window.addEventListener('focus', refreshCourseResults)
    document.addEventListener('visibilitychange', refreshWhenVisible)
    return () => {
      window.removeEventListener('focus', refreshCourseResults)
      document.removeEventListener('visibilitychange', refreshWhenVisible)
    }
  }, [refreshCourseResults])

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

  function updateEditField(field, value) {
    setEditForm((current) => ({ ...current, [field]: value }))
  }

  function cancelEdit() {
    setEditForm(courseToForm(course))
    setEditError(null)
    setShowEditForm(false)
  }

  async function handleEditCourse(event) {
    event.preventDefault()
    setEditError(null)
    setEditMessage(null)

    if (
      !editForm.name.trim() ||
      !editForm.code.trim() ||
      !editForm.teacherId ||
      !editForm.gradeLevel.trim() ||
      !editForm.term.trim() ||
      !editForm.schoolYear.trim()
    ) {
      setEditError('Course name, code, teacher, grade level, term, and school year are required.')
      return
    }

    setSavingEdit(true)
    try {
      await updateCourse(courseId, editForm)
      const refreshed = await getCourse(courseId)
      setCourse(refreshed)
      setEditForm(courseToForm(refreshed))
      setEditMessage('Course updated.')
      setShowEditForm(false)
      try {
        const refreshedTeacher = await getTeacher(refreshed.teacher_id)
        setTeacher(refreshedTeacher)
      } catch {
        setTeacher(allTeachers.find((item) => item.id === refreshed.teacher_id) || null)
      }
    } catch (err) {
      setEditError(err.message)
    } finally {
      setSavingEdit(false)
    }
  }

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
      setShowEnrollForm(false)
    } catch (err) {
      setEnrollError(err.message)
    } finally {
      setEnrolling(false)
    }
  }

  async function handleUnenrollStudent(student) {
    const studentName = `${student.first_name} ${student.last_name}`
    const confirmed = window.confirm(`Unenroll ${studentName} (#${student.student_number}) from ${course.code}?`)
    if (!confirmed) return

    setEnrollError(null)
    setEnrollMessage(null)
    setUnenrollingStudentId(student.id)
    try {
      await unenrollStudentFromCourse(courseId, student.id)
      const refreshed = await listCourseStudents(courseId)
      setStudents(refreshed)
      setEnrollMessage('Student unenrolled.')
    } catch (err) {
      setEnrollError(err.message)
    } finally {
      setUnenrollingStudentId(null)
    }
  }

  function updateGradeItemField(field, value) {
    setGradeItemForm((current) => ({ ...current, [field]: value }))
  }

  function updateEditGradeItemField(field, value) {
    setEditGradeItemForm((current) => ({ ...current, [field]: value }))
  }

  async function handleAddGradeItem(event) {
    event.preventDefault()
    setGradeItemError(null)
    setGradeItemMessage(null)

    const maxScore = Number(gradeItemForm.maxScore)
    const weight = Number(gradeItemForm.weight)
    if (
      !gradeItemForm.title.trim() ||
      !gradeItemForm.category.trim() ||
      !gradeItemForm.term.trim() ||
      !Number.isFinite(maxScore) ||
      !Number.isFinite(weight)
    ) {
      setGradeItemError('Title, category, max score, weight, and term are required.')
      return
    }
    if (maxScore <= 0) {
      setGradeItemError('Max score must be greater than 0.')
      return
    }
    if (weight <= 0 || weight > 1) {
      setGradeItemError('Weight must be greater than 0 and at most 1.')
      return
    }

    setAddingGradeItem(true)
    try {
      await createGradeItem(courseId, gradeItemForm)
      const refreshed = await listGradeItems(courseId)
      setGradeItems(refreshed)
      setGradeItemForm({
        ...EMPTY_GRADE_ITEM_FORM,
        term: gradeItemForm.term.trim(),
      })
      setGradeItemMessage('Grade item added.')
      setShowGradeItemForm(false)
    } catch (err) {
      setGradeItemError(err.message)
    } finally {
      setAddingGradeItem(false)
    }
  }

  async function handleEditGradeItem(event, gradeItemId) {
    event.preventDefault()
    setGradeItemEditError(null)
    setGradeItemMessage(null)

    const maxScore = Number(editGradeItemForm.maxScore)
    const weight = Number(editGradeItemForm.weight)
    if (
      !editGradeItemForm.title.trim() ||
      !editGradeItemForm.category.trim() ||
      !editGradeItemForm.term.trim() ||
      !Number.isFinite(maxScore) ||
      !Number.isFinite(weight)
    ) {
      setGradeItemEditError('Title, category, max score, weight, and term are required.')
      return
    }
    if (maxScore <= 0) {
      setGradeItemEditError('Max score must be greater than 0.')
      return
    }
    if (weight <= 0 || weight > 1) {
      setGradeItemEditError('Weight must be greater than 0 and at most 1.')
      return
    }

    setSavingGradeItemEdit(true)
    try {
      await updateGradeItem(gradeItemId, editGradeItemForm)
      const refreshed = await listGradeItems(courseId)
      setGradeItems(refreshed)
      setGradeItemMessage('Grade item updated.')
      setEditingGradeItemId(null)
      setEditGradeItemForm(gradeItemToForm(null))
    } catch (err) {
      setGradeItemEditError(err.message)
    } finally {
      setSavingGradeItemEdit(false)
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

  const totalWeight = gradeItems.reduce((sum, item) => sum + Number(item.weight || 0), 0)
  const isWeightReady = Math.abs(totalWeight - 1) <= WEIGHT_TOLERANCE
  const weightSummary = isWeightReady
    ? `Grade item weights total ${formatWeight(totalWeight)}. Recalculation is ready.`
    : totalWeight < 1
      ? `Grade item weights total ${formatWeight(totalWeight)}. Missing ${formatWeight(1 - totalWeight)} before recalculation will work correctly.`
      : `Grade item weights total ${formatWeight(totalWeight)}. Over by ${formatWeight(totalWeight - 1)} before recalculation will work correctly.`

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
      {!showEditForm && (
        <div className="grade-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              setEditError(null)
              setEditMessage(null)
              setEditForm(courseToForm(course))
              setShowEditForm(true)
            }}
          >
            Edit
          </button>
        </div>
      )}
      {editMessage && <p className="grade-summary">{editMessage}</p>}
      {showEditForm && (
        <form className="card admin-form" onSubmit={handleEditCourse}>
          <label className="field">
            <span>Course name</span>
            <input
              value={editForm.name}
              onChange={(event) => updateEditField('name', event.target.value)}
              disabled={savingEdit}
              required
            />
          </label>

          <label className="field">
            <span>Course code</span>
            <input
              value={editForm.code}
              onChange={(event) => updateEditField('code', event.target.value)}
              disabled={savingEdit}
              required
            />
          </label>

          <label className="field">
            <span>Teacher</span>
            <select
              className="grade-input"
              value={editForm.teacherId}
              onChange={(event) => updateEditField('teacherId', event.target.value)}
              disabled={savingEdit}
              required
              style={{ width: '100%', textAlign: 'left' }}
            >
              {allTeachers.length === 0 ? (
                <option value={editForm.teacherId}>
                  {teacher ? `${teacher.name} — ${teacher.email}` : 'Current teacher'}
                </option>
              ) : (
                allTeachers.map((teacherOption) => (
                  <option key={teacherOption.id} value={teacherOption.id}>
                    {teacherOption.name} — {teacherOption.email} — #{teacherOption.employee_number}
                  </option>
                ))
              )}
            </select>
          </label>

          <label className="field">
            <span>Grade level</span>
            <input
              value={editForm.gradeLevel}
              onChange={(event) => updateEditField('gradeLevel', event.target.value)}
              disabled={savingEdit}
              list="course-edit-grade-level-options"
              required
            />
          </label>

          <label className="field">
            <span>Term</span>
            <input
              value={editForm.term}
              onChange={(event) => updateEditField('term', event.target.value)}
              disabled={savingEdit}
              list="course-edit-term-options"
              required
            />
          </label>

          <label className="field">
            <span>School year</span>
            <input
              value={editForm.schoolYear}
              onChange={(event) => updateEditField('schoolYear', event.target.value)}
              disabled={savingEdit}
              list="course-edit-school-year-options"
              required
            />
          </label>

          <datalist id="course-edit-grade-level-options">
            {GRADE_LEVEL_SUGGESTIONS.map((value) => (
              <option key={value} value={value} />
            ))}
          </datalist>
          <datalist id="course-edit-term-options">
            {TERM_SUGGESTIONS.map((value) => (
              <option key={value} value={value} />
            ))}
          </datalist>
          <datalist id="course-edit-school-year-options">
            {SCHOOL_YEAR_SUGGESTIONS.map((value) => (
              <option key={value} value={value} />
            ))}
          </datalist>

          <div className="grade-actions">
            <button type="submit" className="btn btn-primary" disabled={savingEdit}>
              {savingEdit ? 'Saving...' : 'Save changes'}
            </button>
            <button type="button" className="btn btn-ghost" disabled={savingEdit} onClick={cancelEdit}>
              Cancel
            </button>
          </div>
          {editError && <ErrorBanner message={editError} />}
        </form>
      )}

      <h3 className="section-title">Enrolled students</h3>
      {!showEnrollForm && (
        <div className="grade-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              setEnrollError(null)
              setEnrollMessage(null)
              setShowEnrollForm(true)
            }}
          >
            Enroll student
          </button>
        </div>
      )}
      {enrollMessage && <p className="grade-summary">{enrollMessage}</p>}
      {enrollError && !showEnrollForm && <ErrorBanner message={enrollError} />}
      {showEnrollForm && (
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
            <button
              type="button"
              className="btn btn-ghost"
              disabled={enrolling}
              onClick={() => {
                setShowEnrollForm(false)
                setEnrollError(null)
              }}
            >
              Cancel
            </button>
          </div>
          {enrollError && <ErrorBanner message={enrollError} />}
        </form>
      )}

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
                    <button
                      type="button"
                      className="btn btn-ghost"
                      disabled={unenrollingStudentId === student.id}
                      onClick={() => handleUnenrollStudent(student)}
                    >
                      {unenrollingStudentId === student.id ? 'Unenrolling...' : 'Unenroll'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3 className="section-title">Grade items</h3>
      {!showGradeItemForm && (
        <div className="grade-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              setGradeItemError(null)
              setGradeItemMessage(null)
              setEditingGradeItemId(null)
              setGradeItemEditError(null)
              setShowGradeItemForm(true)
            }}
          >
            Add grade item
          </button>
        </div>
      )}
      {gradeItemMessage && <p className="grade-summary">{gradeItemMessage}</p>}
      <div className="state state-empty weight-summary">
        <strong>{weightSummary}</strong>
        <p>Weights should add up to 1.00, for example 0.30 = 30%.</p>
      </div>
      {showGradeItemForm && (
        <form className="card admin-form" onSubmit={handleAddGradeItem}>
          <label className="field">
            <span>Title</span>
            <input
              value={gradeItemForm.title}
              onChange={(event) => updateGradeItemField('title', event.target.value)}
              disabled={addingGradeItem}
              list="grade-item-title-options"
              required
            />
          </label>

          <label className="field">
            <span>Category</span>
            <input
              value={gradeItemForm.category}
              onChange={(event) => updateGradeItemField('category', event.target.value)}
              disabled={addingGradeItem}
              list="grade-item-category-options"
              required
            />
          </label>

          <label className="field">
            <span>Max score</span>
            <input
              type="number"
              min="0"
              step="any"
              value={gradeItemForm.maxScore}
              onChange={(event) => updateGradeItemField('maxScore', event.target.value)}
              disabled={addingGradeItem}
              required
            />
          </label>

          <label className="field">
            <span>Weight</span>
            <input
              type="number"
              min="0.01"
              max="1"
              step="0.01"
              value={gradeItemForm.weight}
              onChange={(event) => updateGradeItemField('weight', event.target.value)}
              disabled={addingGradeItem}
              required
            />
            <p className="muted">0.30 = 30%</p>
          </label>

          <label className="field">
            <span>Term</span>
            <input
              value={gradeItemForm.term}
              onChange={(event) => updateGradeItemField('term', event.target.value)}
              disabled={addingGradeItem}
              list="grade-item-term-options"
              required
            />
          </label>

          <datalist id="grade-item-title-options">
            {GRADE_ITEM_SUGGESTIONS.map((value) => (
              <option key={value} value={value} />
            ))}
          </datalist>
          <datalist id="grade-item-category-options">
            {GRADE_ITEM_SUGGESTIONS.map((value) => (
              <option key={value} value={value} />
            ))}
          </datalist>
          <datalist id="grade-item-term-options">
            {TERM_SUGGESTIONS.map((value) => (
              <option key={value} value={value} />
            ))}
          </datalist>

          <div className="grade-actions">
            <button type="submit" className="btn btn-primary" disabled={addingGradeItem}>
              {addingGradeItem ? 'Adding...' : 'Add grade item'}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              disabled={addingGradeItem}
              onClick={() => {
                setShowGradeItemForm(false)
                setGradeItemError(null)
              }}
            >
              Cancel
            </button>
          </div>
          {gradeItemError && <ErrorBanner message={gradeItemError} />}
        </form>
      )}

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
                <th></th>
              </tr>
            </thead>
            <tbody>
              {gradeItems.map((item) => (
                <Fragment key={item.id}>
                  <tr>
                    <td>{item.title}</td>
                    <td className="nowrap">{item.category}</td>
                    <td className="num">{item.max_score}</td>
                    <td className="num">{item.weight}</td>
                    <td className="nowrap">{item.term}</td>
                    <td className="nowrap">{item.due_date || '—'}</td>
                    <td className="nowrap">
                      <button
                        type="button"
                        className="btn btn-ghost"
                        disabled={savingGradeItemEdit}
                        onClick={() => {
                          setShowGradeItemForm(false)
                          setGradeItemError(null)
                          setGradeItemMessage(null)
                          setGradeItemEditError(null)
                          setEditGradeItemForm(gradeItemToForm(item))
                          setEditingGradeItemId(item.id)
                        }}
                      >
                        Edit
                      </button>
                    </td>
                  </tr>
                  {editingGradeItemId === item.id && (
                    <tr>
                      <td colSpan="7">
                        <form className="card admin-form" onSubmit={(event) => handleEditGradeItem(event, item.id)}>
                          <label className="field">
                            <span>Title</span>
                            <input
                              value={editGradeItemForm.title}
                              onChange={(event) => updateEditGradeItemField('title', event.target.value)}
                              disabled={savingGradeItemEdit}
                              list="grade-item-edit-title-options"
                              required
                            />
                          </label>

                          <label className="field">
                            <span>Category</span>
                            <input
                              value={editGradeItemForm.category}
                              onChange={(event) => updateEditGradeItemField('category', event.target.value)}
                              disabled={savingGradeItemEdit}
                              list="grade-item-edit-category-options"
                              required
                            />
                          </label>

                          <label className="field">
                            <span>Max score</span>
                            <input
                              type="number"
                              min="0.01"
                              step="any"
                              value={editGradeItemForm.maxScore}
                              onChange={(event) => updateEditGradeItemField('maxScore', event.target.value)}
                              disabled={savingGradeItemEdit}
                              required
                            />
                          </label>

                          <label className="field">
                            <span>Weight</span>
                            <input
                              type="number"
                              min="0.01"
                              max="1"
                              step="0.01"
                              value={editGradeItemForm.weight}
                              onChange={(event) => updateEditGradeItemField('weight', event.target.value)}
                              disabled={savingGradeItemEdit}
                              required
                            />
                            <p className="muted">0.30 = 30%</p>
                          </label>

                          <label className="field">
                            <span>Term</span>
                            <input
                              value={editGradeItemForm.term}
                              onChange={(event) => updateEditGradeItemField('term', event.target.value)}
                              disabled={savingGradeItemEdit}
                              list="grade-item-edit-term-options"
                              required
                            />
                          </label>

                          <label className="field">
                            <span>Due date</span>
                            <input
                              type="date"
                              value={editGradeItemForm.dueDate}
                              onChange={(event) => updateEditGradeItemField('dueDate', event.target.value)}
                              disabled={savingGradeItemEdit}
                            />
                          </label>

                          <datalist id="grade-item-edit-title-options">
                            {GRADE_ITEM_SUGGESTIONS.map((value) => (
                              <option key={value} value={value} />
                            ))}
                          </datalist>
                          <datalist id="grade-item-edit-category-options">
                            {GRADE_ITEM_SUGGESTIONS.map((value) => (
                              <option key={value} value={value} />
                            ))}
                          </datalist>
                          <datalist id="grade-item-edit-term-options">
                            {TERM_SUGGESTIONS.map((value) => (
                              <option key={value} value={value} />
                            ))}
                          </datalist>

                          <div className="grade-actions">
                            <button type="submit" className="btn btn-primary" disabled={savingGradeItemEdit}>
                              {savingGradeItemEdit ? 'Saving...' : 'Save changes'}
                            </button>
                            <button
                              type="button"
                              className="btn btn-ghost"
                              disabled={savingGradeItemEdit}
                              onClick={() => {
                                setEditingGradeItemId(null)
                                setEditGradeItemForm(gradeItemToForm(null))
                                setGradeItemEditError(null)
                              }}
                            >
                              Cancel
                            </button>
                          </div>
                          {gradeItemEditError && <ErrorBanner message={gradeItemEditError} />}
                        </form>
                      </td>
                    </tr>
                  )}
                </Fragment>
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
