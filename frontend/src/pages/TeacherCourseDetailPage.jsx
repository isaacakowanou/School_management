import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getCourse, listCourseStudents } from '../api/courses.js'
import { createGradeItem, listGradeItems, updateGradeItem } from '../api/gradeItems.js'
import { listCourseGrades } from '../api/grades.js'
import {
  calculateCourseResults,
  calculateSelectedCourseResults,
  listCourseResults,
} from '../api/courseResults.js'
import { formatReportAverage } from '../utils/format.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'
import GradeEntryTable from '../components/GradeEntryTable.jsx'
import TermSelect from '../components/TermSelect.jsx'

const EMPTY_GRADE_ITEM_FORM = {
  title: '',
  category: '',
  maxScore: '20',
  weight: '',
  term: '',
  dueDate: '',
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
const WEIGHT_TOLERANCE = 0.005

function formatWeight(value) {
  return value.toFixed(2)
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

function validateGradeItemForm(form) {
  const maxScore = Number(form.maxScore)
  const weight = Number(form.weight)
  if (
    !form.title.trim() ||
    !form.category.trim() ||
    !form.term.trim() ||
    !Number.isFinite(maxScore) ||
    !Number.isFinite(weight)
  ) {
    return 'Title, category, max score, weight, and term are required.'
  }
  if (maxScore <= 0) return 'Max score must be greater than 0.'
  if (weight <= 0 || weight > 1) return 'Weight must be greater than 0 and at most 1.'
  return null
}

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
  const [showGradeItemForm, setShowGradeItemForm] = useState(false)
  const [gradeItemForm, setGradeItemForm] = useState(EMPTY_GRADE_ITEM_FORM)
  const [addingGradeItem, setAddingGradeItem] = useState(false)
  const [gradeItemError, setGradeItemError] = useState(null)
  const [gradeItemMessage, setGradeItemMessage] = useState(null)
  const [editingGradeItemId, setEditingGradeItemId] = useState(null)
  const [editGradeItemForm, setEditGradeItemForm] = useState(gradeItemToForm(null))
  const [savingGradeItemEdit, setSavingGradeItemEdit] = useState(false)
  const [gradeItemEditError, setGradeItemEditError] = useState(null)

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
    setShowGradeItemForm(false)
    setGradeItemForm(EMPTY_GRADE_ITEM_FORM)
    setAddingGradeItem(false)
    setGradeItemError(null)
    setGradeItemMessage(null)
    setEditingGradeItemId(null)
    setEditGradeItemForm(gradeItemToForm(null))
    setSavingGradeItemEdit(false)
    setGradeItemEditError(null)

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
        setGradeItemForm((current) => ({
          ...current,
          term: current.term || c.term || '',
        }))
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

  function updateGradeItemField(field, value) {
    setGradeItemForm((current) => ({ ...current, [field]: value }))
  }

  function updateEditGradeItemField(field, value) {
    setEditGradeItemForm((current) => ({ ...current, [field]: value }))
  }

  async function refreshGradeItems() {
    const refreshed = await listGradeItems(courseId)
    setGradeItems(refreshed)
    return refreshed
  }

  function openAddGradeItemForm() {
    setShowGradeItemForm(true)
    setGradeItemError(null)
    setGradeItemMessage(null)
    setEditingGradeItemId(null)
    setGradeItemEditError(null)
  }

  function cancelAddGradeItem() {
    setShowGradeItemForm(false)
    setGradeItemError(null)
  }

  async function handleAddGradeItem(event) {
    event.preventDefault()
    setGradeItemError(null)
    setGradeItemMessage(null)

    const validationError = validateGradeItemForm(gradeItemForm)
    if (validationError) {
      setGradeItemError(validationError)
      return
    }

    setAddingGradeItem(true)
    try {
      await createGradeItem(courseId, gradeItemForm)
      await refreshGradeItems()
      setGradeItemForm({
        ...EMPTY_GRADE_ITEM_FORM,
        term: gradeItemForm.term.trim() || course?.term || '',
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

    const validationError = validateGradeItemForm(editGradeItemForm)
    if (validationError) {
      setGradeItemEditError(validationError)
      return
    }

    setSavingGradeItemEdit(true)
    try {
      await updateGradeItem(gradeItemId, editGradeItemForm)
      await refreshGradeItems()
      setGradeItemMessage('Grade item updated.')
      setEditingGradeItemId(null)
      setEditGradeItemForm(gradeItemToForm(null))
    } catch (err) {
      setGradeItemEditError(err.message)
    } finally {
      setSavingGradeItemEdit(false)
    }
  }

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

  const gradeItemList = gradeItems || []
  const totalWeight = gradeItemList.reduce((sum, item) => sum + Number(item.weight || 0), 0)
  const isWeightReady = Math.abs(totalWeight - 1) <= WEIGHT_TOLERANCE
  const weightSummary = isWeightReady
    ? `Grade item weights total ${formatWeight(totalWeight)}. Recalculation is ready.`
    : totalWeight < 1
      ? `Grade item weights total ${formatWeight(totalWeight)}. Missing ${formatWeight(1 - totalWeight)} before recalculation will work correctly.`
      : `Grade item weights total ${formatWeight(totalWeight)}. Over by ${formatWeight(totalWeight - 1)} before recalculation will work correctly.`

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
          {!showGradeItemForm && (
            <div className="grade-actions">
              <button type="button" className="btn btn-primary" onClick={openAddGradeItemForm}>
                Add grade item
              </button>
            </div>
          )}
          {gradeItemMessage && <p className="grade-summary">{gradeItemMessage}</p>}
          <div className="state state-empty weight-summary">
            <strong>{weightSummary}</strong>
            <p>Weights should add up to 1.00, for example 0.30 = 30%.</p>
          </div>

          <datalist id="teacher-grade-item-title-options">
            {GRADE_ITEM_SUGGESTIONS.map((value) => (
              <option key={value} value={value} />
            ))}
          </datalist>
          <datalist id="teacher-grade-item-category-options">
            {GRADE_ITEM_SUGGESTIONS.map((value) => (
              <option key={value} value={value} />
            ))}
          </datalist>

          {showGradeItemForm && (
            <form className="card admin-form" onSubmit={handleAddGradeItem}>
              <label className="field">
                <span>Title</span>
                <input
                  value={gradeItemForm.title}
                  onChange={(event) => updateGradeItemField('title', event.target.value)}
                  disabled={addingGradeItem}
                  list="teacher-grade-item-title-options"
                  required
                />
              </label>

              <label className="field">
                <span>Category</span>
                <input
                  value={gradeItemForm.category}
                  onChange={(event) => updateGradeItemField('category', event.target.value)}
                  disabled={addingGradeItem}
                  list="teacher-grade-item-category-options"
                  required
                />
              </label>

              <label className="field">
                <span>Max score</span>
                <input
                  type="number"
                  min="0.01"
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
                <TermSelect
                  value={gradeItemForm.term}
                  onChange={(value) => updateGradeItemField('term', value)}
                  disabled={addingGradeItem}
                />
              </label>

              <label className="field">
                <span>Due date</span>
                <input
                  type="date"
                  value={gradeItemForm.dueDate}
                  onChange={(event) => updateGradeItemField('dueDate', event.target.value)}
                  disabled={addingGradeItem}
                />
              </label>

              <div className="grade-actions">
                <button type="submit" className="btn btn-primary" disabled={addingGradeItem}>
                  {addingGradeItem ? 'Adding…' : 'Add grade item'}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  disabled={addingGradeItem}
                  onClick={cancelAddGradeItem}
                >
                  Cancel
                </button>
              </div>
              {gradeItemError && <ErrorBanner message={gradeItemError} />}
            </form>
          )}

          {gradeItems.length === 0 ? (
            <Empty message="This course has no grade items yet." />
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
                        <td>{item.category}</td>
                        <td className="num">{item.max_score}</td>
                        <td className="num">{item.weight}</td>
                        <td>{item.term}</td>
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
                                  list="teacher-grade-item-title-options"
                                  required
                                />
                              </label>

                              <label className="field">
                                <span>Category</span>
                                <input
                                  value={editGradeItemForm.category}
                                  onChange={(event) => updateEditGradeItemField('category', event.target.value)}
                                  disabled={savingGradeItemEdit}
                                  list="teacher-grade-item-category-options"
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
                                <TermSelect
                                  value={editGradeItemForm.term}
                                  onChange={(value) => updateEditGradeItemField('term', value)}
                                  disabled={savingGradeItemEdit}
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

                              <div className="grade-actions">
                                <button type="submit" className="btn btn-primary" disabled={savingGradeItemEdit}>
                                  {savingGradeItemEdit ? 'Saving…' : 'Save changes'}
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
                      <td className="num">{formatReportAverage(result.average, result.scale)}</td>
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
